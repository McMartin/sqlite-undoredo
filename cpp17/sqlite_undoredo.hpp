// Copyright 2021 Alain Martin
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Translation of the TCL example code from https://www.sqlite.org/undoredo.html.

#pragma once

#include <sqlitelib.h>

#include <optional>
#include <regex>
#include <stdexcept>
#include <string>
#include <vector>


struct SQLiteUndoRedo
{
  sqlitelib::Sqlite& db;
  explicit SQLiteUndoRedo(sqlitelib::Sqlite& s) : db{s} {}

  //! Start up the undo/redo system
  //!
  //! Arguments should be one or more database tables (in the database
  //! associated with the handle "db") whose changes are to be recorded for
  //! undo/redo purposes.
  template <typename... Args>
  void activate(Args... args) {
    if (_undo.active) return;
    _create_triggers(db, args...);
    _undo.undostack = {};
    _undo.redostack = {};
    _undo.active = 1;
    _undo.freeze = -1;
    _start_interval();
  }

  //! Halt the undo/redo system and delete the undo/redo stacks
  void deactivate() {
    if (!_undo.active) return;
    _drop_triggers(db);
    _undo.undostack = {};
    _undo.redostack = {};
    _undo.active = 0;
    _undo.freeze = -1;
  }

  //! Stop accepting database changes into the undo stack
  //!
  //! From the point when this routine is called up until the next unfreeze,
  //! new database changes are rejected from the undo stack.
  void freeze() {
    if (!_undo.freeze.has_value()) return;
    if (_undo.freeze >= 0) {
      throw std::runtime_error("recursive call to SQLiteUndoRedo::freeze");
    }
    _undo.freeze = db.execute_value<int>("SELECT coalesce(max(seq),0) FROM undolog");
  }

  //! Begin accepting undo actions again.
  void unfreeze() {
    using namespace std::string_literals;
    if (!_undo.freeze.has_value()) return;
    if (_undo.freeze < 0) {
      throw std::runtime_error("called SQLiteUndoRedo::unfreeze while not frozen");
    }
    db.execute(
        ("DELETE FROM undolog WHERE seq>"s + std::to_string(*_undo.freeze)).c_str());
    _undo.freeze = -1;
  }

  //! Something undoable has happened
  //!
  //! This routine is called whenever an undoable action occurs.  Arrangements
  //! are made to invoke ::undo::barrier no later than the next idle moment.
  void event() {
    if (_undo.pending.empty()) {
      throw std::runtime_error("Not implemented");
      // set _undo(pending) after idle ::undo::barrier
    }
  }

  //! Create an undo barrier right now.
  void barrier() {
    try {
      // after cancel $_undo(pending)
    } catch (const std::exception&) {
    }
    _undo.pending = {};
    if (!_undo.active) {
      // refresh();
      return;
    }
    auto end = db.execute_value<int>("SELECT coalesce(max(seq),0) FROM undolog");
    if (_undo.freeze >= 0 && end > _undo.freeze) {
      end = *_undo.freeze;
    }
    auto begin = _undo.firstlog;
    _start_interval();
    if (begin == _undo.firstlog) {
      // refresh();
      return;
    }
    _undo.undostack.push_back({begin, end});
    _undo.redostack = {};
    // refresh();
  }

  //! Do a single step of undo
  void undo() {
    _step(&Undo::undostack, &Undo::redostack);
  }

  //! Redo a single step
  void redo() {
    _step(&Undo::redostack, &Undo::undostack);
  }

  //!  Update the status of controls after a database change
  //!
  //! The undo module calls this routine after any undo/redo in order to
  //! cause controls gray out appropriately depending on the current state
  //! of the database.  This routine works by invoking the status_refresh
  //! module in all top-level namespaces.
  void refresh() {
    throw std::runtime_error("Not implemented");
    // set body {}
    // foreach ns namespace children :: {
    //   if {info proc ${ns}::status_refresh==""} continue
    //   append body ${ns}::status_refresh\n
    // }
    // proc ::undo::refresh {} $body
    // refresh
  }

  //!  Redraw everything based on the current database
  //!
  //! The undo module calls this routine after any undo/redo in order to
  //! cause the screen to be completely redrawn based on the current database
  //! contents.  This is accomplished by calling the "reload" module in
  //! every top-level namespace other than ::undo.
  void reload_all() {
    throw std::runtime_error("Not implemented");
    // set body {}
    // foreach ns namespace children :: {
    //   if {info proc ${ns}::reload==""} continue
    //   append body ${ns}::reload\n
    // }
    // proc ::undo::reload_all {} $body
    // reload_all
  }

  //! state information
  struct Undo
  {
    int active = 0;
    std::vector<std::pair<int, int>> undostack = {};
    std::vector<std::pair<int, int>> redostack = {};
    std::vector<int> pending = {};
    int firstlog = 1;
    std::vector<int> startstate = {};

    std::optional<int> freeze;
  } _undo;

  //! Enable and/or disable menu options a buttons
  void status_refresh() {
    if (!_undo.active || _undo.undostack.size() == 0) {
      throw std::runtime_error("Not implemented");
      // .mb.edit entryconfig Undo -state disabled
      // .bb.undo config -state disabled
    } else {
      throw std::runtime_error("Not implemented");
      // .mb.edit entryconfig Undo -state normal
      // .bb.undo config -state normal
    }
    if (!_undo.active || _undo.redostack.size() == 0) {
      throw std::runtime_error("Not implemented");
      // .mb.edit entryconfig Redo -state disabled
      // .bb.redo config -state disabled
    } else {
      throw std::runtime_error("Not implemented");
      // .mb.edit entryconfig Redo -state normal
      // .bb.redo config -state normal
    }
  }

  //!  Create change recording triggers for all tables listed
  //!
  //! Create a temporary table in the database named "undolog".  Create
  //! triggers that fire on any insert, delete, or update of TABLE1, TABLE2,
  //! .... When those triggers fire, insert records in undolog that contain SQL
  //! text for statements that will undo the insert, delete, or update.
  template <typename... Args>
  static void _create_triggers(sqlitelib::Sqlite& db, Args... args) {
    using namespace std::string_literals;
    try {
      db.execute("DROP TABLE undolog");
    } catch (const std::exception&) {
    }
    db.execute("CREATE TEMP TABLE undolog(seq integer primary key, sql text)");
    for (const auto& tbl : {args...}) {
      auto collist = db.execute<int, std::string, std::string, int, int, int>(
          ("pragma table_info("s + tbl + ")").c_str());
      auto sql =
          "CREATE TEMP TRIGGER _"s + tbl + "_it AFTER INSERT ON " + tbl + " BEGIN\n";
      sql += "  INSERT INTO undolog VALUES(NULL,";
      sql += "'DELETE FROM "s + tbl + " WHERE rowid='||new.rowid);\nEND;";
      db.execute(sql.c_str());

      sql = "CREATE TEMP TRIGGER _"s + tbl + "_ut AFTER UPDATE ON " + tbl + " BEGIN\n";
      sql += "  INSERT INTO undolog VALUES(NULL,";
      sql += "'UPDATE "s + tbl + " ";
      auto sep = "SET ";
      for (const auto& [x1, name, x2, x3, x4, x5] : collist) {
        sql += sep + name + "='||quote(old." + name + ")||'";
        sep = ",";
      }
      sql += " WHERE rowid='||old.rowid);\nEND;\n";
      db.execute(sql.c_str());

      sql = "CREATE TEMP TRIGGER _"s + tbl + "_dt BEFORE DELETE ON " + tbl + " BEGIN\n";
      sql += "  INSERT INTO undolog VALUES(NULL,";
      sql += "'INSERT INTO "s + tbl + "(rowid";
      for (const auto& [x1, name, x2, x3, x4, x5] : collist) {
        sql += "," + name;
      }
      sql += ") VALUES('||old.rowid||'";
      for (const auto& [x1, name, x2, x3, x4, x5] : collist) {
        sql += ",'||quote(old." + name + ")||'";
      }
      sql += ")');\nEND;\n";
      db.execute(sql.c_str());
    }
  }

  //!  Drop all of the triggers that _create_triggers created
  static void _drop_triggers(sqlitelib::Sqlite& db) {
    using namespace std::string_literals;
    auto tlist = db.execute<std::string>("SELECT name FROM sqlite_temp_schema"
                                         " WHERE type='trigger'");
    for (const auto& trigger : tlist) {
      if (!std::regex_match(trigger, std::regex{"_.*_(i|u|d)t$"})) continue;
      db.execute(("DROP TRIGGER "s + trigger + ";").c_str());
    }
    try {
      db.execute("DROP TABLE undolog");
    } catch (const std::exception&) {
    }
  }

  //! Record the starting conditions of an undo interval
  void _start_interval() {
    _undo.firstlog = db.execute_value<int>("SELECT coalesce(max(seq),0)+1 FROM undolog");
  }

  //! Do a single step of undo or redo
  //!
  //! For an undo V1=="undostack" and V2=="redostack".  For a redo,
  //! V1=="redostack" and V2=="undostack".
  void _step(std::vector<std::pair<int, int>> Undo::*v1,
             std::vector<std::pair<int, int>> Undo::*v2) {
    using namespace std::string_literals;
    auto op = (_undo.*v1).back();
    (_undo.*v1).pop_back();
    auto [begin, end] = op;
    db.execute("BEGIN");
    auto q1 = "SELECT sql FROM undolog WHERE seq>="s + std::to_string(begin) +
              " AND seq<=" + std::to_string(end) + " ORDER BY seq DESC";
    auto sqllist = db.execute<std::string>(q1.c_str());
    db.execute(("DELETE FROM undolog WHERE seq>="s + std::to_string(begin) +
                " AND seq<=" + std::to_string(end))
                   .c_str());
    _undo.firstlog = db.execute_value<int>("SELECT coalesce(max(seq),0)+1 FROM undolog");
    for (const auto& sql : sqllist) {
      db.execute(sql.c_str());
    }
    db.execute("COMMIT");
    // reload_all();

    end = db.execute_value<int>("SELECT coalesce(max(seq),0) FROM undolog");
    begin = _undo.firstlog;
    (_undo.*v2).push_back({begin, end});
    _start_interval();
    // refresh();
  }
};
