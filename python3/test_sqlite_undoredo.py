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

from sqlite_undoredo import SQLiteUndoRedo


class SQLiteUndoRedoTest(unittest.TestCase):

    def setUp(self):
        self.db_connection = apsw.Connection(':memory:')

        self.test_db = self.db_connection.cursor()
        self.test_db.execute("CREATE TABLE tbl1(a)")
        self.test_db.execute("CREATE TABLE tbl2(b)")

        self.sqlur = SQLiteUndoRedo(self.test_db)

    def tearDown(self):
        try:
            self.test_db.execute("DROP TABLE undolog")
        except apsw.SQLError:
            pass

        self.db_connection.close()

    def test_activate_one_table(self):
        with mock.patch.object(self.sqlur, '_create_triggers') as mock_create_triggers:
            with mock.patch.object(self.sqlur, '_start_interval') as mock_start_interval:
                self.sqlur.activate('tbl1')

        mock_create_triggers.assert_called_with('tbl1')

        self.assertEqual(self.sqlur._stack['undo'], [])
        self.assertEqual(self.sqlur._stack['redo'], [])
        self.assertEqual(self.sqlur._active, True)

        mock_start_interval.assert_called_with()

    def test_activate_several_tables(self):
        with mock.patch.object(self.sqlur, '_create_triggers') as mock_create_triggers:
            with mock.patch.object(self.sqlur, '_start_interval') as mock_start_interval:
                self.sqlur.activate('tbl1', 'tbl2')

        mock_create_triggers.assert_called_with('tbl1', 'tbl2')

        self.assertEqual(self.sqlur._stack['undo'], [])
        self.assertEqual(self.sqlur._stack['redo'], [])
        self.assertEqual(self.sqlur._active, True)

        mock_start_interval.assert_called_with()

    def test_activate_while_active(self):
        self.assertEqual(self.sqlur._active, False)
        self.sqlur.activate()
        self.assertEqual(self.sqlur._active, True)

        with mock.patch.object(self.sqlur, '_create_triggers') as mock_create_triggers:
            with mock.patch.object(self.sqlur, '_start_interval') as mock_start_interval:
                self.sqlur.activate()

        mock_create_triggers.assert_not_called()
        mock_start_interval.assert_not_called()
        self.assertEqual(self.sqlur._active, True)

    def test_deactivate(self):
        self.sqlur.activate('tbl1')

        with mock.patch.object(self.sqlur, '_drop_triggers') as mock_drop_triggers:
            self.sqlur.deactivate()

        mock_drop_triggers.assert_called_with()

        self.assertEqual(self.sqlur._stack['undo'], [])
        self.assertEqual(self.sqlur._stack['redo'], [])
        self.assertEqual(self.sqlur._active, False)

    def test_deactivate_while_not_active(self):
        self.assertEqual(self.sqlur._active, False)

        with mock.patch.object(self.sqlur, '_drop_triggers') as mock_drop_triggers:
            self.sqlur.deactivate()

        mock_drop_triggers.assert_not_called()

    def test_barrier(self):
        self.sqlur.activate('tbl1')

        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.assertEqual(self.sqlur._stack['undo'], [[1, 1]])
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.sqlur.barrier()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 1], [2, 2]])

    def test_barrier_several_changes(self):
        self.sqlur.activate('tbl1')

        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.sqlur.barrier()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 2]])

    def test_barrier_while_not_active(self):
        self.assertEqual(self.sqlur._active, False)

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.barrier()

        mock_db.execute.assert_not_called()

        self.sqlur.activate()

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.barrier()

        self.assertEqual(mock_db.execute.call_count, 2)

    def test_barrier_after_no_changes(self):
        self.sqlur.activate('tbl1')

        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.assertEqual(self.sqlur._stack['undo'], [[1, 1]])

        self.sqlur.barrier()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 1]])

    def test_undo(self):
        with mock.patch.object(self.sqlur, '_step') as mock_step:
            self.sqlur.undo()

        mock_step.assert_called_with('undo', 'redo')

    def test_undo_insert(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._stack['undo'], [])
        self.assertEqual(self.sqlur._stack['redo'], [[1, 1]])
        self.assertEqual(self.sqlur._firstlog, 2)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

    def test_undo_update(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(42,)])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 1]])
        self.assertEqual(self.sqlur._stack['redo'], [[2, 2]])
        self.assertEqual(self.sqlur._firstlog, 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test_undo_delete(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 1]])
        self.assertEqual(self.sqlur._stack['redo'], [[2, 2]])
        self.assertEqual(self.sqlur._firstlog, 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test_undo_several_changes(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(69,)])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._stack['undo'], [])
        self.assertEqual(self.sqlur._stack['redo'], [[1, 4]])
        self.assertEqual(self.sqlur._firstlog, 5)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

    def test_redo(self):
        with mock.patch.object(self.sqlur, '_step') as mock_step:
            self.sqlur.redo()

        mock_step.assert_called_with('redo', 'undo')

    def test_redo_insert(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 1]])
        self.assertEqual(self.sqlur._stack['redo'], [])
        self.assertEqual(self.sqlur._firstlog, 2)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test_redo_update(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 1], [2, 2]])
        self.assertEqual(self.sqlur._stack['redo'], [])
        self.assertEqual(self.sqlur._firstlog, 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(42,)])

    def test_redo_delete(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 1], [2, 2]])
        self.assertEqual(self.sqlur._stack['redo'], [])
        self.assertEqual(self.sqlur._firstlog, 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

    def test_redo_several_changes(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._stack['undo'], [[1, 4]])
        self.assertEqual(self.sqlur._stack['redo'], [])
        self.assertEqual(self.sqlur._firstlog, 5)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(69,)])

    def test___init__(self):
        self.assertIs(self.sqlur._db, self.test_db)
        self.assertEqual(self.sqlur._active, False)
        self.assertEqual(self.sqlur._stack, {'undo': [], 'redo': []})
        self.assertEqual(self.sqlur._firstlog, 1)

    def _get_triggers(self, db):
        return db.execute(
            "SELECT name FROM sqlite_temp_schema WHERE type='trigger'").fetchall()

    def test__create_triggers_no_tables(self):
        self.sqlur._create_triggers()

        self.assertEqual(self._get_triggers(self.test_db), [])

    def test__create_triggers_one_table(self):
        self.sqlur._create_triggers('tbl1')

        self.assertEqual(
            self._get_triggers(self.test_db),
            [('_tbl1_it',), ('_tbl1_ut',), ('_tbl1_dt',)],
        )

    def test__create_triggers_several_tables(self):
        self.sqlur._create_triggers('tbl1', 'tbl2')

        self.assertEqual(len(self._get_triggers(self.test_db)), 6)

    def test__drop_triggers(self):
        self.sqlur._create_triggers('tbl1', 'tbl2')

        self.sqlur._drop_triggers()

        self.assertEqual(self._get_triggers(self.test_db), [])

    def test__start_interval(self):
        self.sqlur.activate('tbl1')

        self.sqlur._start_interval()

        self.assertEqual(self.sqlur._firstlog, 1)

        self.test_db.executemany("INSERT INTO tbl1 VALUES(?)", [(23,), (42,)])
        self.sqlur.barrier()

        self.sqlur._start_interval()

        self.assertEqual(self.sqlur._firstlog, 3)


if __name__ == '__main__':
    unittest.main()
