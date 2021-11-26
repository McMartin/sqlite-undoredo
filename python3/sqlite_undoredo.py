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
        self._cursor.execute("""CREATE TEMP TABLE undo_redo_step(
            id INTEGER PRIMARY KEY, is_redo INTEGER NOT NULL, text TEXT NOT NULL
        )""")
        self._cursor.execute("""CREATE TEMP TABLE undo_redo_action(
            sql TEXT NOT NULL,
            step INTEGER,
            FOREIGN KEY(step) REFERENCES undo_redo_step(id) ON DELETE CASCADE
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

    def commit(self, text):
        uncommitted_actions_count = self._cursor.execute(
            "SELECT COUNT(rowid) FROM undo_redo_action WHERE step IS NULL"
        ).fetchone()[0]

        if uncommitted_actions_count:
            step_id = self._cursor.execute(
                "INSERT INTO undo_redo_step (is_redo, text) VALUES(?, ?) RETURNING id",
                (0, text),
            ).fetchone()[0]
            self._cursor.execute(
                "UPDATE undo_redo_action SET step = ? WHERE step IS NULL",
                (step_id,)
            )
            self._cursor.execute("DELETE FROM undo_redo_step WHERE is_redo = ?", (1,))

    def _step(self, is_redo):
        self._cursor.execute('BEGIN')
        step_id, text = self._cursor.execute(
            "SELECT id, text FROM undo_redo_step WHERE is_redo = ?"
            " ORDER BY rowid DESC LIMIT 1",
            (int(is_redo),),
        ).fetchone()
        sql_statements = self._cursor.execute(
            "SELECT sql FROM undo_redo_action WHERE step = ? ORDER BY rowid DESC",
            (step_id,),
        ).fetchall()
        self._cursor.execute("DELETE FROM undo_redo_step WHERE id = ?", (step_id,))
        for (statement,) in sql_statements:
            self._cursor.execute(statement)
        self._cursor.execute('COMMIT')

        step_id = self._cursor.execute(
            "INSERT INTO undo_redo_step (is_redo, text) VALUES(?, ?) RETURNING id",
            (int(not is_redo), text),
        ).fetchone()[0]
        self._cursor.execute(
            "UPDATE undo_redo_action SET step = ? WHERE step IS NULL", (step_id,)
        )

    def undo(self):
        self._step(is_redo=False)

    def redo(self):
        self._step(is_redo=True)
