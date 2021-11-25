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
            self._cursor.execute("DROP TABLE undo_redo_action")
        except apsw.SQLError:
            pass
        self._cursor.execute("CREATE TEMP TABLE undo_redo_action(sql TEXT NOT NULL)")
        self._cursor.execute("CREATE TEMP TABLE undo_step("
            " first_action INTEGER NOT NULL,"
            " last_action INTEGER NOT NULL,"
            " CHECK (first_action <= last_action))"
        )
        self._cursor.execute("CREATE TEMP TABLE redo_step("
            " first_action INTEGER NOT NULL,"
            " last_action INTEGER NOT NULL,"
            " CHECK (first_action <= last_action))"
        )

        self._previous_end = (self._get_last_undo_redo_action() + 1)

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
                INSERT INTO undo_redo_action VALUES(
                    'DELETE FROM {table} WHERE rowid='||NEW.rowid
                );
            END;

            CREATE TEMP TRIGGER undo_{table}_update AFTER UPDATE ON {table} BEGIN
                INSERT INTO undo_redo_action VALUES(
                    'UPDATE {table} SET {update_values} WHERE rowid='||OLD.rowid
                );
            END;

            CREATE TEMP TRIGGER undo_{table}_delete AFTER DELETE ON {table} BEGIN
                INSERT INTO undo_redo_action VALUES(
                    'INSERT INTO {table} ({insert_columns}) VALUES({insert_values})'
                );
            END;
        """)

    def uninstall(self, table):
        self._cursor.execute(f"DROP TRIGGER IF EXISTS undo_{table}_insert")
        self._cursor.execute(f"DROP TRIGGER IF EXISTS undo_{table}_update")
        self._cursor.execute(f"DROP TRIGGER IF EXISTS undo_{table}_delete")

    def _get_last_undo_redo_action(self):
        return self._cursor.execute(
            "SELECT coalesce(max(rowid), 0) FROM undo_redo_action"
        ).fetchone()[0]

    def commit(self):
        end = (self._get_last_undo_redo_action() + 1)
        if self._previous_end != end:
            self._cursor.execute(
                "INSERT INTO undo_step (first_action, last_action) VALUES(?, ?)",
                (self._previous_end, self._get_last_undo_redo_action()),
            )
            self._cursor.execute("DELETE FROM redo_step")
            self._previous_end = end

    def _step(self, lhs_table, rhs_table):
        self._cursor.execute('BEGIN')
        rowid, first_action, last_action = self._cursor.execute(
            f"SELECT rowid, first_action, last_action FROM {lhs_table} ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        self._cursor.execute(f"DELETE FROM {lhs_table} WHERE rowid = {rowid}")
        condition = f"rowid >= {first_action} AND rowid <= {last_action}"
        sql_statements = self._cursor.execute(
            f"SELECT sql FROM undo_redo_action WHERE {condition} ORDER BY rowid DESC"
        ).fetchall()
        self._cursor.execute(f"DELETE FROM undo_redo_action WHERE {condition}")
        end_before_replay = (self._get_last_undo_redo_action() + 1)
        for (statement,) in sql_statements:
            self._cursor.execute(statement)
        self._cursor.execute('COMMIT')

        self._cursor.execute(
            f"INSERT INTO {rhs_table} (first_action, last_action) VALUES(?, ?)",
            (end_before_replay, self._get_last_undo_redo_action()),
        )

        self._previous_end = (self._get_last_undo_redo_action() + 1)

    def undo(self):
        self._step('undo_step', 'redo_step')

    def redo(self):
        self._step('redo_step', 'undo_step')
