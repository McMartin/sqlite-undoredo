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
        self._cursor.execute("PRAGMA foreign_keys = ON")
        self._cursor.execute("""CREATE TEMP TABLE undo_step(
            id INTEGER PRIMARY KEY, text TEXT NOT NULL
        )""")
        self._cursor.execute("""CREATE TEMP TABLE redo_step(
            id INTEGER PRIMARY KEY, text TEXT NOT NULL
        )""")
        self._cursor.execute("""CREATE TEMP TABLE undo_redo_action(
            sql TEXT NOT NULL,
            undo_step INTEGER,
            redo_step INTEGER,
            FOREIGN KEY(undo_step) REFERENCES undo_step(id) ON DELETE CASCADE,
            FOREIGN KEY(redo_step) REFERENCES redo_step(id) ON DELETE CASCADE,
            CHECK(undo_step IS NULL OR redo_step IS NULL)
        )""")

    def install(self, table):
        column_names = [
            column[1]
            for column in self._cursor.execute(f"pragma table_info({table})").fetchall()
        ]

        update_values = ", ".join(
            [f"{name}='||quote(OLD.{name})||'" for name in column_names]
        )

        insert_columns = ", ".join(["rowid"] + column_names)
        insert_values = ", ".join(
            ["'||OLD.rowid||'"] + [f"'||quote(OLD.{name})||'" for name in column_names]
        )

        self._cursor.execute(f"""
            CREATE TEMP TRIGGER undo_{table}_insert AFTER INSERT ON {table} BEGIN
                INSERT INTO undo_redo_action (sql) VALUES(
                    'DELETE FROM {table} WHERE rowid='||NEW.rowid
                );
            END;

            CREATE TEMP TRIGGER undo_{table}_update AFTER UPDATE ON {table} BEGIN
                INSERT INTO undo_redo_action (sql) VALUES(
                    'UPDATE {table} SET {update_values} WHERE rowid='||OLD.rowid
                );
            END;

            CREATE TEMP TRIGGER undo_{table}_delete AFTER DELETE ON {table} BEGIN
                INSERT INTO undo_redo_action (sql) VALUES(
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

    def commit(self, text):
        uncommitted_actions_count = self._cursor.execute(
            "SELECT COUNT(rowid) FROM undo_redo_action"
            " WHERE undo_step IS NULL AND redo_step IS NULL"
        ).fetchone()[0]

        if uncommitted_actions_count:
            undo_step_id = self._cursor.execute(
                "INSERT INTO undo_step (text) VALUES(?) RETURNING id", (text,)
            ).fetchone()[0]
            self._cursor.execute(
                "UPDATE undo_redo_action SET undo_step = ?"
                " WHERE undo_step IS NULL AND redo_step IS NULL",
                (undo_step_id,)
            )
            self._cursor.execute("DELETE FROM redo_step")

    def _step(self, lhs_table, rhs_table):
        self._cursor.execute('BEGIN')
        step_id, text = self._cursor.execute(
            f"SELECT id, text FROM {lhs_table} ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        sql_statements = self._cursor.execute(
            f"SELECT sql FROM undo_redo_action WHERE {lhs_table} = ? ORDER BY rowid DESC",
            (step_id,),
        ).fetchall()
        self._cursor.execute(f"DELETE FROM {lhs_table} WHERE id = ?", (step_id,))
        for (statement,) in sql_statements:
            self._cursor.execute(statement)
        self._cursor.execute('COMMIT')

        step_id = self._cursor.execute(
            f"INSERT INTO {rhs_table} (text) VALUES(?) RETURNING id", (text,)
        ).fetchone()[0]
        self._cursor.execute(
            f"UPDATE undo_redo_action SET {rhs_table} = ?"
            " WHERE undo_step IS NULL AND redo_step IS NULL",
            (step_id,)
        )

    def undo(self):
        self._step('undo_step', 'redo_step')

    def redo(self):
        self._step('redo_step', 'undo_step')
