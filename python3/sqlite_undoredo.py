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
            self._cursor.execute("DROP TABLE undo_action")
        except apsw.SQLError:
            pass
        self._cursor.execute("CREATE TEMP TABLE undo_action(sql TEXT)")

        self._undo_stack = []
        self._redo_stack = []
        self._previous_end = self._get_end()

    def install(self, table):
        column_names = [
            column[1]
            for column in self._cursor.execute(f"pragma table_info({table})").fetchall()
        ]

        update_values = ", ".join(
            [f"{name}='||quote(OLD.{name})||'" for name in column_names]
        )

        insert_columns = ", ".join(["rowid"] + column_names)
        insert_values =  ", ".join(
            ["'||OLD.rowid||'"] + [f"'||quote(OLD.{name})||'" for name in column_names]
        )

        self._cursor.execute(f"""
            CREATE TEMP TRIGGER undo_{table}_insert AFTER INSERT ON {table} BEGIN
                INSERT INTO undo_action VALUES(
                    'DELETE FROM {table} WHERE rowid='||NEW.rowid
                );
            END;

            CREATE TEMP TRIGGER undo_{table}_update AFTER UPDATE ON {table} BEGIN
                INSERT INTO undo_action VALUES(
                    'UPDATE {table} SET {update_values} WHERE rowid='||OLD.rowid
                );
            END;

            CREATE TEMP TRIGGER undo_{table}_delete AFTER DELETE ON {table} BEGIN
                INSERT INTO undo_action VALUES(
                    'INSERT INTO {table} ({insert_columns}) VALUES({insert_values})'
                );
            END;
        """)

    def uninstall(self, table):
        self._cursor.execute(f"DROP TRIGGER IF EXISTS undo_{table}_insert")
        self._cursor.execute(f"DROP TRIGGER IF EXISTS undo_{table}_update")
        self._cursor.execute(f"DROP TRIGGER IF EXISTS undo_{table}_delete")

    def _get_last_undo_action(self):
        return self._cursor.execute(
            "SELECT coalesce(max(rowid), 0) FROM undo_action"
        ).fetchone()[0]

    def _get_end(self):
        return self._cursor.execute(
            "SELECT coalesce(max(rowid), 0) + 1 FROM undo_action"
        ).fetchone()[0]

    def commit(self):
        end = self._get_end()
        if self._previous_end != end:
            self._undo_stack.append((self._previous_end, self._get_last_undo_action()))
            self._redo_stack = []
            self._previous_end = end

    def _step(self, lhs, rhs):
        first_action, last_action = lhs.pop()
        self._cursor.execute('BEGIN')
        condition = f"rowid >= {first_action} AND rowid <= {last_action}"
        sql_statements = self._cursor.execute(
            f"SELECT sql FROM undo_action WHERE {condition} ORDER BY rowid DESC"
        ).fetchall()
        self._cursor.execute(f"DELETE FROM undo_action WHERE {condition}")
        end_before_replay = self._get_end()
        for (statement,) in sql_statements:
            self._cursor.execute(statement)
        self._cursor.execute('COMMIT')

        rhs.append((end_before_replay, self._get_last_undo_action()))
        self._previous_end = self._get_end()

    def undo(self):
        self._step(self._undo_stack, self._redo_stack)

    def redo(self):
        self._step(self._redo_stack, self._undo_stack)
