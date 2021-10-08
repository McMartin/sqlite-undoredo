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


class SQLiteUndoHistory:

    def __init__(self, db):
        self._cursor = db

        try:
            self._cursor.execute("DROP TABLE undo_actions")
        except apsw.SQLError:
            pass
        self._cursor.execute("CREATE TEMP TABLE undo_actions(sql TEXT)")

        self._stack = {'undo': [], 'redo': []}
        self._previous_end = 1

    def install(self, tbl):
        column_names = [
            column[1]
            for column in self._cursor.execute(f"pragma table_info({tbl})").fetchall()
        ]

        update_values = ", ".join(
            [f"{name}='||quote(OLD.{name})||'" for name in column_names]
        )

        insert_columns = ", ".join(["rowid"] + column_names)
        insert_values =  ", ".join(
            ["'||OLD.rowid||'"] + [f"'||quote(OLD.{name})||'" for name in column_names]
        )

        sql = f"""
        CREATE TEMP TRIGGER _{tbl}_it AFTER INSERT ON {tbl} BEGIN
            INSERT INTO undo_actions VALUES(
                'DELETE FROM {tbl} WHERE rowid='||NEW.rowid
            );
        END;

        CREATE TEMP TRIGGER _{tbl}_ut AFTER UPDATE ON {tbl} BEGIN
            INSERT INTO undo_actions VALUES(
                'UPDATE {tbl} SET {update_values} WHERE rowid='||OLD.rowid
            );
        END;

        CREATE TEMP TRIGGER _{tbl}_dt AFTER DELETE ON {tbl} BEGIN
            INSERT INTO undo_actions VALUES(
                'INSERT INTO {tbl} ({insert_columns}) VALUES({insert_values})'
            );
        END;
        """

        self._cursor.execute(sql)

    def uninstall(self, tbl):
        self._cursor.execute(f"DROP TRIGGER IF EXISTS _{tbl}_it")
        self._cursor.execute(f"DROP TRIGGER IF EXISTS _{tbl}_ut")
        self._cursor.execute(f"DROP TRIGGER IF EXISTS _{tbl}_dt")

    def _get_end(self):
        return self._cursor.execute(
            "SELECT coalesce(max(rowid),0)+1 FROM undo_actions").fetchone()[0]

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
        self._cursor.execute('BEGIN')
        q1 = f"SELECT sql FROM undo_actions WHERE rowid>={begin} AND rowid<{end}" \
             " ORDER BY rowid DESC"
        sqllist = self._cursor.execute(q1).fetchall()
        self._cursor.execute(f"DELETE FROM undo_actions WHERE rowid>={begin} AND rowid<{end}")
        rhs_begin = self._get_end()
        for (sql,) in sqllist:
            self._cursor.execute(sql)
        self._cursor.execute('COMMIT')

        rhs_end = self._get_end()
        self._stack[rhs].append([rhs_begin, rhs_end])
        self._previous_end = rhs_end

    def undo(self):
        self._step('undo', 'redo')

    def redo(self):
        self._step('redo', 'undo')
