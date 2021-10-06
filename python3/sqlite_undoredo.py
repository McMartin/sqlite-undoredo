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

"""Translation of the TCL example code from https://www.sqlite.org/undoredo.html."""

import re
import sys

import apsw


if sys.version_info < (3, 6):
    sys.exit('Python version 3.6 or later is required')


class SQLiteUndoRedo:

    def activate(self, *args):
        _undo = self._undo
        if _undo['active']:
            return
        self._create_triggers(*args)
        _undo['undostack'] = []
        _undo['redostack'] = []
        _undo['active'] = 1
        _undo['freeze'] = -1
        self._start_interval()

    def deactivate(self):
        _undo = self._undo
        if not _undo['active']:
            return
        self._drop_triggers()
        _undo['undostack'] = []
        _undo['redostack'] = []
        _undo['active'] = 0
        _undo['freeze'] = -1

    def freeze(self):
        _undo = self._undo
        if 'freeze' not in _undo:
            return
        if _undo['freeze'] >= 0:
            raise Exception("recursive call to SQLiteUndoRedo.freeze")
        _undo['freeze'] = self._db.execute(
            "SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]

    def unfreeze(self):
        _undo = self._undo
        if 'freeze' not in _undo:
            return
        if _undo['freeze'] < 0:
            raise Exception("called SQLiteUndoRedo.unfreeze while not frozen")
        self._db.execute(f"DELETE FROM undolog WHERE seq>{_undo['freeze']}")
        _undo['freeze'] = -1

    def barrier(self):
        _undo = self._undo
        _undo['pending'] = []
        if not _undo['active']:
            return
        end = self._db.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
        if _undo['freeze'] >= 0 and end > _undo['freeze']:
            end = _undo['freeze']
        begin = _undo['firstlog']
        self._start_interval()
        if begin == _undo['firstlog']:
            return
        _undo['undostack'].append([begin, end])
        _undo['redostack'] = []

    def undo(self):
        self._step('undostack', 'redostack')

    def redo(self):
        self._step('redostack', 'undostack')

    def __init__(self, db):
        self._db = db

        self._undo = {}
        self._undo['active'] = 0
        self._undo['undostack'] = []
        self._undo['redostack'] = []
        self._undo['pending'] = []
        self._undo['firstlog'] = 1
        self._undo['startstate'] = []

    def _create_triggers(self, *args):
        try:
            self._db.execute("DROP TABLE undolog")
        except apsw.SQLError:
            pass
        self._db.execute("CREATE TEMP TABLE undolog(seq integer primary key, sql text)")
        for tbl in args:
            collist = self._db.execute(f"pragma table_info({tbl})").fetchall()
            sql = f"CREATE TEMP TRIGGER _{tbl}_it AFTER INSERT ON {tbl} BEGIN\n"
            sql += "  INSERT INTO undolog VALUES(NULL,"
            sql += f"'DELETE FROM {tbl} WHERE rowid='||new.rowid);\nEND;\n"

            sql += f"CREATE TEMP TRIGGER _{tbl}_ut AFTER UPDATE ON {tbl} BEGIN\n"
            sql += "  INSERT INTO undolog VALUES(NULL,"
            sql += f"'UPDATE {tbl} "
            sep = "SET "
            for (x1, name, x2, x3, x4, x5) in collist:
                sql += f"{sep}{name}='||quote(old.{name})||'"
                sep = ","
            sql += " WHERE rowid='||old.rowid);\nEND;\n"

            sql += f"CREATE TEMP TRIGGER _{tbl}_dt BEFORE DELETE ON {tbl} BEGIN\n"
            sql += "  INSERT INTO undolog VALUES(NULL,"
            sql += f"'INSERT INTO {tbl}(rowid"
            for (x1, name, x2, x3, x4, x5) in collist:
                sql += f",{name}"
            sql += ") VALUES('||old.rowid||'"
            for (x1, name, x2, x3, x4, x5) in collist:
                sql += f",'||quote(old.{name})||'"
            sql += ")');\nEND;\n"

            self._db.execute(sql)

    def _drop_triggers(self):
        tlist = self._db.execute(
            "SELECT name FROM sqlite_temp_schema WHERE type='trigger'").fetchall()
        for (trigger,) in tlist:
            if not re.match("_.*_(i|u|d)t$", trigger):
                continue
            self._db.execute(f"DROP TRIGGER {trigger};")
        try:
            self._db.execute("DROP TABLE undolog")
        except apsw.SQLError:
            pass

    def _start_interval(self):
        _undo = self._undo
        _undo['firstlog'] = self._db.execute(
            "SELECT coalesce(max(seq),0)+1 FROM undolog").fetchone()[0]

    def _step(self, v1, v2):
        _undo = self._undo
        op = _undo[v1][-1]
        _undo[v1] = _undo[v1][0:-1]
        (begin, end) = op
        self._db.execute('BEGIN')
        q1 = f"SELECT sql FROM undolog WHERE seq>={begin} AND seq<={end}" \
             " ORDER BY seq DESC"
        sqllist = self._db.execute(q1).fetchall()
        self._db.execute(f"DELETE FROM undolog WHERE seq>={begin} AND seq<={end}")
        _undo['firstlog'] = self._db.execute(
            "SELECT coalesce(max(seq),0)+1 FROM undolog").fetchone()[0]
        for (sql,) in sqllist:
            self._db.execute(sql)
        self._db.execute('COMMIT')

        end = self._db.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
        begin = _undo['firstlog']
        _undo[v2].append([begin, end])
        self._start_interval()
