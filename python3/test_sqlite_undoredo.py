# Copyright 2019, 2021 Alain Martin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

from unittest import mock

import apsw

from sqlite_undoredo import SQLiteUndoHistory


class SQLiteUndoRedoTest(unittest.TestCase):

    def setUp(self):
        self.db_connection = apsw.Connection(':memory:')

        self.test_cursor = self.db_connection.cursor()
        self.test_cursor.execute("CREATE TABLE tbl1(a)")
        self.test_cursor.execute("CREATE TABLE tbl2(b)")

        self.history = SQLiteUndoHistory(self.test_cursor)

    def tearDown(self):
        try:
            self.test_cursor.execute("DROP TABLE undolog")
        except apsw.SQLError:
            pass

        self.db_connection.close()

    def test_record_undo_step(self):
        self.history.install('tbl1')

        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()
        self.assertEqual(self.history._stack['undo'], [[1, 2]])
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.history.record_undo_step()

        self.assertEqual(self.history._stack['undo'], [[1, 2], [2, 3]])

    def test_record_undo_step_several_changes(self):
        self.history.install('tbl1')

        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.history.record_undo_step()

        self.assertEqual(self.history._stack['undo'], [[1, 3]])

    def test_record_undo_step_after_no_changes(self):
        self.history.install('tbl1')

        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()
        self.assertEqual(self.history._stack['undo'], [[1, 2]])

        self.history.record_undo_step()

        self.assertEqual(self.history._stack['undo'], [[1, 2]])

    def test_undo(self):
        with mock.patch.object(self.history, '_step') as mock_step:
            self.history.undo()

        mock_step.assert_called_with('undo', 'redo')

    def test_undo_insert(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.history.undo()

        self.assertEqual(self.history._stack['undo'], [])
        self.assertEqual(self.history._stack['redo'], [[1, 2]])
        self.assertEqual(self.history._previous_end, 2)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [])

    def test_undo_update(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.history.record_undo_step()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(42,)])

        self.history.undo()

        self.assertEqual(self.history._stack['undo'], [[1, 2]])
        self.assertEqual(self.history._stack['redo'], [[2, 3]])
        self.assertEqual(self.history._previous_end, 3)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test_undo_delete(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.record_undo_step()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [])

        self.history.undo()

        self.assertEqual(self.history._stack['undo'], [[1, 2]])
        self.assertEqual(self.history._stack['redo'], [[2, 3]])
        self.assertEqual(self.history._previous_end, 3)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test_undo_several_changes(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.record_undo_step()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(69,)])

        self.history.undo()

        self.assertEqual(self.history._stack['undo'], [])
        self.assertEqual(self.history._stack['redo'], [[1, 5]])
        self.assertEqual(self.history._previous_end, 5)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [])

    def test_redo(self):
        with mock.patch.object(self.history, '_step') as mock_step:
            self.history.redo()

        mock_step.assert_called_with('redo', 'undo')

    def test_redo_insert(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()
        self.history.undo()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [])

        self.history.redo()

        self.assertEqual(self.history._stack['undo'], [[1, 2]])
        self.assertEqual(self.history._stack['redo'], [])
        self.assertEqual(self.history._previous_end, 2)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test_redo_update(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.history.record_undo_step()
        self.history.undo()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.history.redo()

        self.assertEqual(self.history._stack['undo'], [[1, 2], [2, 3]])
        self.assertEqual(self.history._stack['redo'], [])
        self.assertEqual(self.history._previous_end, 3)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(42,)])

    def test_redo_delete(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.record_undo_step()
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.record_undo_step()
        self.history.undo()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.history.redo()

        self.assertEqual(self.history._stack['undo'], [[1, 2], [2, 3]])
        self.assertEqual(self.history._stack['redo'], [])
        self.assertEqual(self.history._previous_end, 3)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [])

    def test_redo_several_changes(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.record_undo_step()
        self.history.undo()

        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [])

        self.history.redo()

        self.assertEqual(self.history._stack['undo'], [[1, 5]])
        self.assertEqual(self.history._stack['redo'], [])
        self.assertEqual(self.history._previous_end, 5)
        self.assertEqual(self.test_cursor.execute("SELECT * FROM tbl1").fetchall(), [(69,)])

    def test___init__(self):
        self.assertIs(self.history._cursor, self.test_cursor)
        self.assertEqual(self.history._stack, {'undo': [], 'redo': []})
        self.assertEqual(self.history._previous_end, 1)

    def _get_triggers(self, db):
        return db.execute(
            "SELECT name FROM sqlite_temp_schema WHERE type='trigger'").fetchall()

    def test_install(self):
        self.history.install('tbl1')

        self.assertEqual(
            self._get_triggers(self.test_cursor),
            [('_tbl1_it',), ('_tbl1_ut',), ('_tbl1_dt',)],
        )

    def test_uninstall(self):
        self.history.install('tbl1')

        self.history.uninstall('tbl1')

        self.assertEqual(self._get_triggers(self.test_cursor), [])

    def test__get_end(self):
        self.history.install('tbl1')

        self.assertEqual(self.history._get_end(), 1)

        self.test_cursor.executemany("INSERT INTO tbl1 VALUES(?)", [(23,), (42,)])

        self.assertEqual(self.history._get_end(), 3)

        self.history.record_undo_step()

        self.assertEqual(self.history._get_end(), 3)


if __name__ == '__main__':
    unittest.main()
