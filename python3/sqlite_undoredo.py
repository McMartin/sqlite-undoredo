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

    def __init__(self, db):
        self._db = db

        try:
            self._db.execute("DROP TABLE undo_actions")
        except apsw.SQLError:
            pass
        self._db.execute("CREATE TEMP TABLE undo_actions(seq integer primary key, sql text)")

        self._stack = {'undo': [], 'redo': []}
        self._previous_end = 1

    def install(self, *args):
        for tbl in args:
            collist = self._db.execute(f"pragma table_info({tbl})").fetchall()
            sql = f"CREATE TEMP TRIGGER _{tbl}_it AFTER INSERT ON {tbl} BEGIN\n"
            sql += "  INSERT INTO undo_actions VALUES(NULL,"
            sql += f"'DELETE FROM {tbl} WHERE rowid='||new.rowid);\nEND;\n"

            sql += f"CREATE TEMP TRIGGER _{tbl}_ut AFTER UPDATE ON {tbl} BEGIN\n"
            sql += "  INSERT INTO undo_actions VALUES(NULL,"
            sql += f"'UPDATE {tbl} "
            sep = "SET "
            for (x1, name, x2, x3, x4, x5) in collist:
                sql += f"{sep}{name}='||quote(old.{name})||'"
                sep = ","
            sql += " WHERE rowid='||old.rowid);\nEND;\n"

            sql += f"CREATE TEMP TRIGGER _{tbl}_dt BEFORE DELETE ON {tbl} BEGIN\n"
            sql += "  INSERT INTO undo_actions VALUES(NULL,"
            sql += f"'INSERT INTO {tbl}(rowid"
            for (x1, name, x2, x3, x4, x5) in collist:
                sql += f",{name}"
            sql += ") VALUES('||old.rowid||'"
            for (x1, name, x2, x3, x4, x5) in collist:
                sql += f",'||quote(old.{name})||'"
            sql += ")');\nEND;\n"

            self._db.execute(sql)

    def uninstall(self, *args):
        for tbl in args:
            self._db.execute(f"DROP TRIGGER IF EXISTS _{tbl}_it")
            self._db.execute(f"DROP TRIGGER IF EXISTS _{tbl}_ut")
            self._db.execute(f"DROP TRIGGER IF EXISTS _{tbl}_dt")

    def _get_end(self):
        return self._db.execute(
            "SELECT coalesce(max(seq),0)+1 FROM undo_actions").fetchone()[0]

    def record_undo_step(self):
        begin = self._previous_end
        end = self._get_end()
        if begin == end:
            return
        self._stack['undo'].append([begin, end])
        self._stack['redo'] = []
        self._previous_end = end

    def _step(self, lhs, rhs):
        (begin, end) = self._stack[lhs].pop()
        self._db.execute('BEGIN')
        q1 = f"SELECT sql FROM undo_actions WHERE seq>={begin} AND seq<{end}" \
             " ORDER BY seq DESC"
        sqllist = self._db.execute(q1).fetchall()
        self._db.execute(f"DELETE FROM undo_actions WHERE seq>={begin} AND seq<{end}")
        rhs_begin = self._get_end()
        for (sql,) in sqllist:
            self._db.execute(sql)
        self._db.execute('COMMIT')

        rhs_end = self._get_end()
        self._stack[rhs].append([rhs_begin, rhs_end])
        self._previous_end = rhs_end

    def undo(self):
        self._step('undo', 'redo')

    def redo(self):
        self._step('redo', 'undo')
