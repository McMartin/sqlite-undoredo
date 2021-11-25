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

    def _select_all(self, table):
        return self.test_cursor.execute(f"SELECT * FROM {table}").fetchall()

    def test_commit(self):
        self.history.install('tbl1')

        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")
        self.assertEqual(self._select_all('undo_step'), [(1, 1, "Add 23")])
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.history.commit("Add 42")

        self.assertEqual(
            self._select_all('undo_step'), [(1, 1, "Add 23"), (2, 2, "Add 42")]
        )

    def test_commit_several_changes(self):
        self.history.install('tbl1')

        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.history.commit("Add 23 and 42")

        self.assertEqual(self._select_all('undo_step'), [(1, 2, "Add 23 and 42")])

    def test_commit_after_no_changes(self):
        self.history.install('tbl1')

        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")
        self.assertEqual(self._select_all('undo_step'), [(1, 1, "Add 23")])

        self.history.commit("Nothing")

        self.assertEqual(self._select_all('undo_step'), [(1, 1, "Add 23")])

    def test_undo(self):
        with mock.patch.object(self.history, '_step') as mock_step:
            self.history.undo()

        mock_step.assert_called_with('undo_step', 'redo_step')

    def test_undo_insert(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")

        self.assertEqual(self._select_all('tbl1'), [(23,)])

        self.history.undo()

        self.assertEqual(self._select_all('undo_step'), [])
        self.assertEqual(self._select_all('redo_step'), [(1, 1, "Add 23")])
        self.assertEqual(self._select_all('tbl1'), [])

    def test_undo_update(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.history.commit("Change 23 to 42")

        self.assertEqual(self._select_all('tbl1'), [(42,)])

        self.history.undo()

        self.assertEqual(self._select_all('undo_step'), [(1, 1, "Add 23")])
        self.assertEqual(self._select_all('redo_step'), [(2, 2, "Change 23 to 42")])
        self.assertEqual(self._select_all('tbl1'), [(23,)])

    def test_undo_delete(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.commit("Remove 23")

        self.assertEqual(self._select_all('tbl1'), [])

        self.history.undo()

        self.assertEqual(self._select_all('undo_step'), [(1, 1, "Add 23")])
        self.assertEqual(self._select_all('redo_step'), [(2, 2, "Remove 23")])
        self.assertEqual(self._select_all('tbl1'), [(23,)])

    def test_undo_several_changes(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.commit("Several changes")

        self.assertEqual(self._select_all('tbl1'), [(69,)])

        self.history.undo()

        self.assertEqual(self._select_all('undo_step'), [])
        self.assertEqual(self._select_all('redo_step'), [(1, 4, "Several changes")])
        self.assertEqual(self._select_all('tbl1'), [])

    def test_redo(self):
        with mock.patch.object(self.history, '_step') as mock_step:
            self.history.redo()

        mock_step.assert_called_with('redo_step', 'undo_step')

    def test_redo_insert(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")
        self.history.undo()

        self.assertEqual(self._select_all('tbl1'), [])

        self.history.redo()

        self.assertEqual(self._select_all('undo_step'), [(1, 1, "Add 23")])
        self.assertEqual(self._select_all('redo_step'), [])
        self.assertEqual(self._select_all('tbl1'), [(23,)])

    def test_redo_update(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.history.commit("Change 23 to 42")
        self.history.undo()

        self.assertEqual(self._select_all('tbl1'), [(23,)])

        self.history.redo()

        self.assertEqual(
            self._select_all('undo_step'), [(1, 1, "Add 23"), (2, 2, "Change 23 to 42")]
        )
        self.assertEqual(self._select_all('redo_step'), [])
        self.assertEqual(self._select_all('tbl1'), [(42,)])

    def test_redo_delete(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.history.commit("Add 23")
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.commit("Remove 23")
        self.history.undo()

        self.assertEqual(self._select_all('tbl1'), [(23,)])

        self.history.redo()

        self.assertEqual(
            self._select_all('undo_step'), [(1, 1, "Add 23"), (2, 2, "Remove 23")]
        )
        self.assertEqual(self._select_all('redo_step'), [])
        self.assertEqual(self._select_all('tbl1'), [])

    def test_redo_several_changes(self):
        self.history.install('tbl1')
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_cursor.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_cursor.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_cursor.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.history.commit("Several changes")
        self.history.undo()

        self.assertEqual(self._select_all('tbl1'), [])

        self.history.redo()

        self.assertEqual(self._select_all('undo_step'), [(1, 4, "Several changes")])
        self.assertEqual(self._select_all('redo_step'), [])
        self.assertEqual(self._select_all('tbl1'), [(69,)])

    def test___init__(self):
        self.assertIs(self.history._cursor, self.test_cursor)
        self.assertEqual(self._select_all('undo_step'), [])
        self.assertEqual(self._select_all('redo_step'), [])

    def _get_triggers(self, db):
        return db.execute(
            "SELECT name FROM sqlite_temp_schema WHERE type='trigger'").fetchall()

    def test_install(self):
        self.history.install('tbl1')

        self.assertEqual(
            self._get_triggers(self.test_cursor),
            [('undo_tbl1_insert',), ('undo_tbl1_update',), ('undo_tbl1_delete',)],
        )

    def test_uninstall(self):
        self.history.install('tbl1')

        self.history.uninstall('tbl1')

        self.assertEqual(self._get_triggers(self.test_cursor), [])

    def test__get_last_undo_redo_action(self):
        self.history.install('tbl1')

        self.assertEqual(self.history._get_last_undo_redo_action(), 0)

        self.test_cursor.executemany("INSERT INTO tbl1 VALUES(?)", [(23,), (42,)])

        self.assertEqual(self.history._get_last_undo_redo_action(), 2)

        self.history.commit("Add 23 and 42")

        self.assertEqual(self.history._get_last_undo_redo_action(), 2)


if __name__ == '__main__':
    unittest.main()
