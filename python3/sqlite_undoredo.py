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
        if self._active:
            return
        self._create_triggers(*args)
        self._stack['undo'] = []
        self._stack['redo'] = []
        self._active = True
        self._start_interval()

    def deactivate(self):
        if not self._active:
            return
        self._drop_triggers()
        self._stack['undo'] = []
        self._stack['redo'] = []
        self._active = False

    def barrier(self):
        if not self._active:
            return
        end = self._db.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
        begin = self._firstlog
        self._start_interval()
        if begin == self._firstlog:
            return
        self._stack['undo'].append([begin, end])
        self._stack['redo'] = []

    def undo(self):
        self._step('undo', 'redo')

    def redo(self):
        self._step('redo', 'undo')

    def __init__(self, db):
        self._db = db

        self._active = False
        self._stack = {'undo': [], 'redo': []}
        self._firstlog = 1

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
        self._firstlog = self._db.execute(
            "SELECT coalesce(max(seq),0)+1 FROM undolog").fetchone()[0]

    def _step(self, v1, v2):
        op = self._stack[v1][-1]
        self._stack[v1] = self._stack[v1][0:-1]
        (begin, end) = op
        self._db.execute('BEGIN')
        q1 = f"SELECT sql FROM undolog WHERE seq>={begin} AND seq<={end}" \
             " ORDER BY seq DESC"
        sqllist = self._db.execute(q1).fetchall()
        self._db.execute(f"DELETE FROM undolog WHERE seq>={begin} AND seq<={end}")
        self._firstlog = self._db.execute(
            "SELECT coalesce(max(seq),0)+1 FROM undolog").fetchone()[0]
        for (sql,) in sqllist:
            self._db.execute(sql)
        self._db.execute('COMMIT')

        end = self._db.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
        begin = self._firstlog
        self._stack[v2].append([begin, end])
        self._start_interval()
