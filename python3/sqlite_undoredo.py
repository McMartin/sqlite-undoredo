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
import sqlite3
import sys


if sys.version_info < (3, 6):
    sys.exit('Python version 3.6 or later is required')


class SQLiteUndoRedo:

    def activate(self, *args):
        """Start up the undo/redo system.

        Arguments should be one or more database tables (in the database associated
        with the handle "db") whose changes are to be recorded for undo/redo
        purposes.
        """
        _undo = self._undo
        if _undo['active']:
            return
        self._create_triggers(self._db, *args)
        _undo['undostack'] = []
        _undo['redostack'] = []
        _undo['active'] = 1
        _undo['freeze'] = -1
        self._start_interval()

    def deactivate(self):
        """Halt the undo/redo system and delete the undo/redo stacks."""
        _undo = self._undo
        if not _undo['active']:
            return
        self._drop_triggers(self._db)
        _undo['undostack'] = []
        _undo['redostack'] = []
        _undo['active'] = 0
        _undo['freeze'] = -1

    def freeze(self):
        """Stop accepting database changes into the undo stack.

        From the point when this routine is called up until the next unfreeze,
        new database changes are rejected from the undo stack.
        """
        _undo = self._undo
        if 'freeze' not in _undo:
            return
        if _undo['freeze'] >= 0:
            raise Exception("recursive call to freeze")
        _undo['freeze'] = self._db.execute(
            "SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]

    def unfreeze(self):
        """Begin accepting undo actions again."""
        _undo = self._undo
        if 'freeze' not in _undo:
            return
        if _undo['freeze'] < 0:
            raise Exception("called unfreeze while not frozen")
        self._db.execute(f"DELETE FROM undolog WHERE seq>{_undo['freeze']}")
        _undo['freeze'] = -1

    def event(self):
        """Something undoable has happened.

        This routine is called whenever an undoable action occurs.  Arrangements
        are made to invoke ::undo::barrier no later than the next idle moment.
        """
        _undo = self._undo
        if _undo['pending'] == "":
            raise NotImplementedError
            # set _undo(pending) after idle ::undo::barrier

    def barrier(self):
        """Create an undo barrier right now."""
        _undo = self._undo
        try:
            pass
            # after cancel $_undo(pending)
        except Exception:
            pass
        _undo['pending'] = []
        if not _undo['active']:
            # self.refresh()
            return
        end = self._db.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
        if _undo['freeze'] >= 0 and end > _undo['freeze']:
            end = _undo['freeze']
        begin = _undo['firstlog']
        self._start_interval()
        if begin == _undo['firstlog']:
            # self.refresh()
            return
        _undo['undostack'].append([begin, end])
        _undo['redostack'] = []
        # self.refresh()

    def undo(self):
        """Do a single step of undo."""
        self._step('undostack', 'redostack')

    def redo(self):
        """Redo a single step."""
        self._step('redostack', 'undostack')

    def refresh(self):
        """Update the status of controls after a database change.

        The undo module calls this routine after any undo/redo in order to
        cause controls gray out appropriately depending on the current state
        of the database.  This routine works by invoking the status_refresh
        module in all top-level namespaces.
        """
        raise NotImplementedError
        # set body {}
        # foreach ns namespace children :: {
        #   if {info proc ${ns}::status_refresh==""} continue
        #   append body ${ns}::status_refresh\n
        # }
        # proc ::undo::refresh {} $body
        # refresh

    def reload_all(self):
        """Redraw everything based on the current database.

        The undo module calls this routine after any undo/redo in order to
        cause the screen to be completely redrawn based on the current database
        contents.  This is accomplished by calling the "reload" module in
        every top-level namespace other than ::undo.
        """
        raise NotImplementedError
        # set body {}
        # foreach ns namespace children :: {
        #   if {info proc ${ns}::reload==""} continue
        #   append body ${ns}::reload\n
        # }
        # proc ::undo::reload_all {} $body
        # reload_all

    def __init__(self, db):
        self._db = db

        # state information
        #
        self._undo = {}
        self._undo['active'] = 0
        self._undo['undostack'] = []
        self._undo['redostack'] = []
        self._undo['pending'] = []
        self._undo['firstlog'] = 1
        self._undo['startstate'] = []

    def status_refresh(self):
        """Enable and/or disable menu options a buttons."""
        _undo = self._undo
        if not _undo['active'] or len(_undo['undostack']) == 0:
            raise NotImplementedError
            # .mb.edit entryconfig Undo -state disabled
            # .bb.undo config -state disabled
        else:
            raise NotImplementedError
            # .mb.edit entryconfig Undo -state normal
            # .bb.undo config -state normal
        if not _undo['active'] or len(_undo['redostack']) == 0:
            raise NotImplementedError
            # .mb.edit entryconfig Redo -state disabled
            # .bb.redo config -state disabled
        else:
            raise NotImplementedError
            # .mb.edit entryconfig Redo -state normal
            # .bb.redo config -state normal

    @staticmethod
    def _create_triggers(db, *args):
        """Create change recording triggers for all tables listed.

        Create a temporary table in the database named "undolog".  Create
        triggers that fire on any insert, delete, or update of TABLE1, TABLE2, ....
        When those triggers fire, insert records in undolog that contain
        SQL text for statements that will undo the insert, delete, or update.
        """
        try:
            db.execute("DROP TABLE undolog")
        except sqlite3.OperationalError:
            pass
        db.execute("CREATE TEMP TABLE undolog(seq integer primary key, sql text)")
        for tbl in args:
            collist = db.execute(f"pragma table_info({tbl})").fetchall()
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

            db.executescript(sql)

    @staticmethod
    def _drop_triggers(db):
        """Drop all of the triggers that _create_triggers created."""
        tlist = db.execute(
            "SELECT name FROM sqlite_temp_schema WHERE type='trigger'").fetchall()
        for (trigger,) in tlist:
            if not re.match("_.*_(i|u|d)t$", trigger):
                continue
            db.execute(f"DROP TRIGGER {trigger};")
        try:
            db.execute("DROP TABLE undolog")
        except sqlite3.OperationalError:
            pass

    def _start_interval(self):
        """Record the starting conditions of an undo interval."""
        _undo = self._undo
        _undo['firstlog'] = self._db.execute(
            "SELECT coalesce(max(seq),0)+1 FROM undolog").fetchone()[0]

    def _step(self, v1, v2):
        """Do a single step of undo or redo.

        For an undo V1=="undostack" and V2=="redostack".  For a redo,
        V1=="redostack" and V2=="undostack".
        """
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
        # self.reload_all()

        end = self._db.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
        begin = _undo['firstlog']
        _undo[v2].append([begin, end])
        self._start_interval()
        # self.refresh()
