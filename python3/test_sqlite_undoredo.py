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

import sqlite3
import unittest

from unittest import mock

from sqlite_undoredo import SQLiteUndoRedo


class SQLiteUndoRedoTest(unittest.TestCase):

    def setUp(self):
        self.test_db = sqlite3.connect(':memory:')
        self.test_db.isolation_level = None
        self.test_db.execute("CREATE TABLE tbl1(a)")
        self.test_db.execute("CREATE TABLE tbl2(b)")

        self.sqlur = SQLiteUndoRedo(self.test_db)

    def tearDown(self):
        self.test_db.close()

    def test_activate_one_table(self):
        with mock.patch.object(self.sqlur, '_create_triggers') as mock_create_triggers:
            with mock.patch.object(self.sqlur, '_start_interval') as mock_start_interval:
                self.sqlur.activate('tbl1')

        mock_create_triggers.assert_called_with(self.test_db, 'tbl1')

        self.assertEqual(self.sqlur._undo['undostack'], [])
        self.assertEqual(self.sqlur._undo['redostack'], [])
        self.assertEqual(self.sqlur._undo['active'], 1)
        self.assertEqual(self.sqlur._undo['freeze'], -1)

        mock_start_interval.assert_called_with()

    def test_activate_several_tables(self):
        with mock.patch.object(self.sqlur, '_create_triggers') as mock_create_triggers:
            with mock.patch.object(self.sqlur, '_start_interval') as mock_start_interval:
                self.sqlur.activate('tbl1', 'tbl2')

        mock_create_triggers.assert_called_with(self.test_db, 'tbl1', 'tbl2')

        self.assertEqual(self.sqlur._undo['undostack'], [])
        self.assertEqual(self.sqlur._undo['redostack'], [])
        self.assertEqual(self.sqlur._undo['active'], 1)
        self.assertEqual(self.sqlur._undo['freeze'], -1)

        mock_start_interval.assert_called_with()

    def test_activate_while_active(self):
        self.assertEqual(self.sqlur._undo['active'], 0)
        self.sqlur.activate()
        self.assertEqual(self.sqlur._undo['active'], 1)

        with mock.patch.object(self.sqlur, '_create_triggers') as mock_create_triggers:
            with mock.patch.object(self.sqlur, '_start_interval') as mock_start_interval:
                self.sqlur.activate()

        mock_create_triggers.assert_not_called()
        mock_start_interval.assert_not_called()
        self.assertEqual(self.sqlur._undo['active'], 1)

    def test_deactivate(self):
        self.sqlur.activate('tbl1')

        with mock.patch.object(self.sqlur, '_drop_triggers') as mock_drop_triggers:
            self.sqlur.deactivate()

        mock_drop_triggers.assert_called_with(self.test_db)

        self.assertEqual(self.sqlur._undo['undostack'], [])
        self.assertEqual(self.sqlur._undo['redostack'], [])
        self.assertEqual(self.sqlur._undo['active'], 0)
        self.assertEqual(self.sqlur._undo['freeze'], -1)

    def test_deactivate_while_not_active(self):
        self.assertEqual(self.sqlur._undo['active'], 0)

        with mock.patch.object(self.sqlur, '_drop_triggers') as mock_drop_triggers:
            self.sqlur.deactivate()

        mock_drop_triggers.assert_not_called()

    def test_freeze(self):
        self.sqlur.activate('tbl1')
        self.assertEqual(self.sqlur._undo['freeze'], -1)

        self.test_db.executemany("INSERT INTO tbl1 VALUES(?)", [(23,), (42,)])
        self.sqlur.barrier()

        self.sqlur.freeze()

        self.assertEqual(self.sqlur._undo['freeze'], 2)

    def test_freeze_while_frozen(self):
        self.sqlur.activate('tbl1')
        self.assertEqual(self.sqlur._undo['freeze'], -1)

        self.sqlur.freeze()

        self.assertEqual(self.sqlur._undo['freeze'], 0)

        with self.assertRaises(Exception):
            self.sqlur.freeze()

    def test_freeze_before_activate(self):
        self.assertEqual(self.sqlur._undo['active'], 0)

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.freeze()

        mock_db.execute.assert_not_called()

        self.sqlur.activate()

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.freeze()

        self.assertEqual(mock_db.execute.call_count, 1)

    def test_unfreeze(self):
        self.sqlur.activate('tbl1')
        self.assertEqual(self.sqlur._undo['freeze'], -1)

        self.test_db.executemany("INSERT INTO tbl1 VALUES(?)", [(23,), (42,)])
        self.sqlur.barrier()

        self.sqlur.freeze()
        self.assertEqual(self.sqlur._undo['freeze'], 2)

        self.test_db.executemany("INSERT INTO tbl1 VALUES(?)", [(69,), (404,)])
        self.sqlur.barrier()

        self.assertEqual(len(self.test_db.execute("SELECT * FROM undolog").fetchall()), 4)

        self.sqlur.unfreeze()

        self.assertEqual(len(self.test_db.execute("SELECT * FROM undolog").fetchall()), 2)

        self.assertEqual(self.sqlur._undo['freeze'], -1)

    def test_unfreeze_before_activate(self):
        self.assertEqual(self.sqlur._undo['active'], 0)

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.unfreeze()

        mock_db.execute.assert_not_called()

        self.sqlur.activate()
        self.sqlur.freeze()

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.unfreeze()

        self.assertEqual(mock_db.execute.call_count, 1)

    def test_unfreeze_while_not_frozen(self):
        self.sqlur.activate('tbl1')
        self.assertEqual(self.sqlur._undo['freeze'], -1)

        with self.assertRaises(Exception):
            self.sqlur.unfreeze()

    def test_barrier(self):
        self.sqlur.activate('tbl1')

        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1]])
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.sqlur.barrier()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1], [2, 2]])

    def test_barrier_several_changes(self):
        self.sqlur.activate('tbl1')

        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.sqlur.barrier()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 2]])

    def test_barrier_while_not_active(self):
        self.assertEqual(self.sqlur._undo['active'], 0)

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.barrier()

        mock_db.execute.assert_not_called()

        self.sqlur.activate()

        with mock.patch.object(self.sqlur, '_db') as mock_db:
            self.sqlur.barrier()

        self.assertEqual(mock_db.execute.call_count, 2)

    def test_barrier_while_frozen(self):
        self.sqlur.activate('tbl1')

        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.sqlur.freeze()
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))

        self.sqlur.barrier()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1], [2, 1]])

    def test_barrier_after_no_changes(self):
        self.sqlur.activate('tbl1')

        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1]])

        self.sqlur.barrier()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1]])

    def test_undo(self):
        with mock.patch.object(self.sqlur, '_step') as mock_step:
            self.sqlur.undo()

        mock_step.assert_called_with('undostack', 'redostack')

    def test_redo(self):
        with mock.patch.object(self.sqlur, '_step') as mock_step:
            self.sqlur.redo()

        mock_step.assert_called_with('redostack', 'undostack')

    def test___init__(self):
        self.assertIs(self.sqlur._db, self.test_db)
        self.assertEqual(
            self.sqlur._undo,
            {
                'active': 0,
                'undostack': [],
                'redostack': [],
                'pending': [],
                'firstlog': 1,
                'startstate': [],
            },
        )

    def _get_triggers(self, db):
        return db.execute(
            "SELECT name FROM sqlite_temp_master WHERE type='trigger'").fetchall()

    def test__create_triggers_no_tables(self):
        self.sqlur._create_triggers(self.test_db)

        self.assertEqual(self._get_triggers(self.test_db), [])

    def test__create_triggers_one_table(self):
        self.sqlur._create_triggers(self.test_db, 'tbl1')

        self.assertEqual(
            self._get_triggers(self.test_db),
            [('_tbl1_it',), ('_tbl1_ut',), ('_tbl1_dt',)],
        )

    def test__create_triggers_several_tables(self):
        self.sqlur._create_triggers(self.test_db, 'tbl1', 'tbl2')

        self.assertEqual(len(self._get_triggers(self.test_db)), 6)

    def test__drop_triggers(self):
        self.sqlur._create_triggers(self.test_db, 'tbl1', 'tbl2')

        self.sqlur._drop_triggers(self.test_db)

        self.assertEqual(self._get_triggers(self.test_db), [])

    def test__start_interval(self):
        self.sqlur.activate('tbl1')

        self.sqlur._start_interval()

        self.assertEqual(self.sqlur._undo['firstlog'], 1)

        self.test_db.executemany("INSERT INTO tbl1 VALUES(?)", [(23,), (42,)])
        self.sqlur.barrier()

        self.sqlur._start_interval()

        self.assertEqual(self.sqlur._undo['firstlog'], 3)

    def test__step_undo_insert(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._undo['undostack'], [])
        self.assertEqual(self.sqlur._undo['redostack'], [[1, 1]])
        self.assertEqual(self.sqlur._undo['firstlog'], 2)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

    def test__step_undo_update(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(42,)])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1]])
        self.assertEqual(self.sqlur._undo['redostack'], [[2, 2]])
        self.assertEqual(self.sqlur._undo['firstlog'], 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test__step_undo_delete(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1]])
        self.assertEqual(self.sqlur._undo['redostack'], [[2, 2]])
        self.assertEqual(self.sqlur._undo['firstlog'], 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test__step_undo_several_changes(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(69,)])

        self.sqlur.undo()

        self.assertEqual(self.sqlur._undo['undostack'], [])
        self.assertEqual(self.sqlur._undo['redostack'], [[1, 4]])
        self.assertEqual(self.sqlur._undo['firstlog'], 5)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

    def test__step_redo_insert(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1]])
        self.assertEqual(self.sqlur._undo['redostack'], [])
        self.assertEqual(self.sqlur._undo['firstlog'], 2)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

    def test__step_redo_update(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (42, 23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1], [2, 2]])
        self.assertEqual(self.sqlur._undo['redostack'], [])
        self.assertEqual(self.sqlur._undo['firstlog'], 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(42,)])

    def test__step_redo_delete(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.sqlur.barrier()
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(23,)])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 1], [2, 2]])
        self.assertEqual(self.sqlur._undo['redostack'], [])
        self.assertEqual(self.sqlur._undo['firstlog'], 3)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

    def test__step_redo_several_changes(self):
        self.sqlur.activate('tbl1')
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (23,))
        self.test_db.execute("INSERT INTO tbl1 VALUES(?)", (42,))
        self.test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", (69, 42))
        self.test_db.execute("DELETE FROM tbl1 WHERE a=?", (23,))
        self.sqlur.barrier()
        self.sqlur.undo()

        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [])

        self.sqlur.redo()

        self.assertEqual(self.sqlur._undo['undostack'], [[1, 4]])
        self.assertEqual(self.sqlur._undo['redostack'], [])
        self.assertEqual(self.sqlur._undo['firstlog'], 5)
        self.assertEqual(self.test_db.execute("SELECT * FROM tbl1").fetchall(), [(69,)])


if __name__ == '__main__':
    unittest.main()
