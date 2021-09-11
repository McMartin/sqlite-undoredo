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

#include "sqlite_undoredo.hpp"

#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <sqlitelib.h>


TEST_CASE("SQLiteUndoRedo") {
  sqlitelib::Sqlite test_db{":memory:"};
  test_db.execute("CREATE TABLE tbl1(a)");
  test_db.execute("CREATE TABLE tbl2(a)");

  SQLiteUndoRedo sqlur{test_db};

  SUBCASE("activate - one table") {
    sqlur.activate("tbl1");

    CHECK(sqlur._undo.undostack.empty());
    CHECK(sqlur._undo.redostack.empty());
    CHECK(sqlur._undo.active == 1);
    CHECK(sqlur._undo.freeze == -1);
  }

  SUBCASE("activate - several tables") {
    sqlur.activate("tbl1", "tbl2");

    CHECK(sqlur._undo.undostack.empty());
    CHECK(sqlur._undo.redostack.empty());
    CHECK(sqlur._undo.active == 1);
    CHECK(sqlur._undo.freeze == -1);
  }

  SUBCASE("activate - while active") {
    REQUIRE(sqlur._undo.active == 0);
    sqlur.activate("tbl1");
    CHECK(sqlur._undo.active == 1);

    sqlur.activate("tbl1");

    CHECK(sqlur._undo.active == 1);
  }

  SUBCASE("deactivate") {
    sqlur.activate("tbl1");

    sqlur.deactivate();

    CHECK(sqlur._undo.undostack.empty());
    CHECK(sqlur._undo.redostack.empty());
    CHECK(sqlur._undo.active == 0);
    CHECK(sqlur._undo.freeze == -1);
  }

  SUBCASE("deactivate - while not active") {
    REQUIRE(sqlur._undo.active == 0);

    sqlur.deactivate();
  }

  SUBCASE("freeze") {
    sqlur.activate("tbl1");
    CHECK(sqlur._undo.freeze == -1);

    auto stmt = test_db.prepare("INSERT INTO tbl1 VALUES(?)");
    stmt.execute(23);
    stmt.execute(42);
    sqlur.barrier();

    sqlur.freeze();

    CHECK(sqlur._undo.freeze == 2);
  }

  SUBCASE("freeze - while frozen") {
    sqlur.activate("tbl1");
    CHECK(sqlur._undo.freeze == -1);

    sqlur.freeze();

    CHECK(sqlur._undo.freeze == 0);

    CHECK_THROWS_AS(sqlur.freeze(), std::runtime_error);
  }

  SUBCASE("unfreeze") {
    sqlur.activate("tbl1");
    CHECK(sqlur._undo.freeze == -1);

    auto stmt = test_db.prepare("INSERT INTO tbl1 VALUES(?)");

    stmt.execute(23);
    stmt.execute(42);
    sqlur.barrier();

    sqlur.freeze();
    CHECK(sqlur._undo.freeze == 2);

    stmt.execute(69);
    stmt.execute(404);
    sqlur.barrier();

    CHECK(test_db.execute<int>("SELECT * FROM undolog").size() == 4);

    sqlur.unfreeze();

    CHECK(test_db.execute<int>("SELECT * FROM undolog").size() == 2);

    CHECK(sqlur._undo.freeze == -1);
  }

  SUBCASE("unfreeze - while not frozen") {
    sqlur.activate("tbl1");
    CHECK(sqlur._undo.freeze == -1);

    CHECK_THROWS_AS(sqlur.unfreeze(), std::runtime_error);
  }

  SUBCASE("barrier") {
    sqlur.activate("tbl1");

    auto stmt = test_db.prepare("INSERT INTO tbl1 VALUES(?)");

    stmt.execute(23);
    sqlur.barrier();
    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>({{1, 1}}));
    stmt.execute(42);

    sqlur.barrier();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>({{1, 1}, {2, 2}}));
  }

  SUBCASE("barrier - several changes") {
    sqlur.activate("tbl1");

    auto stmt = test_db.prepare("INSERT INTO tbl1 VALUES(?)");
    stmt.execute(23);
    stmt.execute(42);

    sqlur.barrier();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>({{1, 2}}));
  }

  SUBCASE("barrier - while frozen") {
    sqlur.activate("tbl1");

    auto stmt = test_db.prepare("INSERT INTO tbl1 VALUES(?)");

    stmt.execute(23);
    sqlur.barrier();
    sqlur.freeze();
    stmt.execute(42);

    sqlur.barrier();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>({{1, 1}, {2, 1}}));
  }

  SUBCASE("barrier - after no changes") {
    sqlur.activate("tbl1");

    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    sqlur.barrier();
    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>({{1, 1}}));

    sqlur.barrier();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>({{1, 1}}));
  }

  SUBCASE("undo - insert") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    sqlur.barrier();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{23});

    sqlur.undo();

    CHECK(sqlur._undo.undostack.empty());
    CHECK(sqlur._undo.redostack == std::vector<std::pair<int, int>>{{1, 1}});
    CHECK(sqlur._undo.firstlog == 2);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1").empty());
  }

  SUBCASE("undo - update") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    sqlur.barrier();
    test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", 42, 23);
    sqlur.barrier();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{42});

    sqlur.undo();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>{{1, 1}});
    CHECK(sqlur._undo.redostack == std::vector<std::pair<int, int>>{{2, 2}});
    CHECK(sqlur._undo.firstlog == 3);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{23});
  }

  SUBCASE("undo - delete") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    sqlur.barrier();
    test_db.execute("DELETE FROM tbl1 WHERE a=?", 23);
    sqlur.barrier();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1").empty());

    sqlur.undo();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>{{1, 1}});
    CHECK(sqlur._undo.redostack == std::vector<std::pair<int, int>>{{2, 2}});
    CHECK(sqlur._undo.firstlog == 3);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{23});
  }

  SUBCASE("undo - several changes") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 42);
    test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", 69, 42);
    test_db.execute("DELETE FROM tbl1 WHERE a=?", 23);
    sqlur.barrier();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{69});

    sqlur.undo();

    CHECK(sqlur._undo.undostack.empty());
    CHECK(sqlur._undo.redostack == std::vector<std::pair<int, int>>{{1, 4}});
    CHECK(sqlur._undo.firstlog == 5);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1").empty());
  }

  SUBCASE("redo - insert") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    sqlur.barrier();
    sqlur.undo();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1").empty());

    sqlur.redo();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>{{1, 1}});
    CHECK(sqlur._undo.redostack.empty());
    CHECK(sqlur._undo.firstlog == 2);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{23});
  }

  SUBCASE("redo - update") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    sqlur.barrier();
    test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", 42, 23);
    sqlur.barrier();
    sqlur.undo();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{23});

    sqlur.redo();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>{{1, 1}, {2, 2}});
    CHECK(sqlur._undo.redostack.empty());
    CHECK(sqlur._undo.firstlog == 3);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{42});
  }

  SUBCASE("redo - delete") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    sqlur.barrier();
    test_db.execute("DELETE FROM tbl1 WHERE a=?", 23);
    sqlur.barrier();
    sqlur.undo();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{23});

    sqlur.redo();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>{{1, 1}, {2, 2}});
    CHECK(sqlur._undo.redostack.empty());
    CHECK(sqlur._undo.firstlog == 3);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1").empty());
  }

  SUBCASE("redo - several changes") {
    sqlur.activate("tbl1");
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 23);
    test_db.execute("INSERT INTO tbl1 VALUES(?)", 42);
    test_db.execute("UPDATE tbl1 SET a=? WHERE a=?", 69, 42);
    test_db.execute("DELETE FROM tbl1 WHERE a=?", 23);
    sqlur.barrier();
    sqlur.undo();

    CHECK(test_db.execute<int>("SELECT * FROM tbl1").empty());

    sqlur.redo();

    CHECK(sqlur._undo.undostack == std::vector<std::pair<int, int>>{{1, 4}});
    CHECK(sqlur._undo.redostack.empty());
    CHECK(sqlur._undo.firstlog == 5);
    CHECK(test_db.execute<int>("SELECT * FROM tbl1") == std::vector<int>{69});
  }

  const auto get_triggers = [](sqlitelib::Sqlite& db) {
    return db.execute<std::string>(
        "SELECT name FROM sqlite_temp_master WHERE type='trigger'");
  };

  SUBCASE("_create_triggers - one table") {
    sqlur._create_triggers(test_db, "tbl1");

    CHECK(get_triggers(test_db) ==
          std::vector<std::string>{"_tbl1_it", "_tbl1_ut", "_tbl1_dt"});
  }

  SUBCASE("_create_triggers - several tables") {
    sqlur._create_triggers(test_db, "tbl1", "tbl2");

    CHECK(get_triggers(test_db).size() == 6);
  }

  SUBCASE("_drop_triggers") {
    sqlur._create_triggers(test_db, "tbl1", "tbl2");

    sqlur._drop_triggers(test_db);

    CHECK(get_triggers(test_db).empty());
  }

  SUBCASE("_start_interval") {
    sqlur.activate("tbl1");

    sqlur._start_interval();

    CHECK(sqlur._undo.firstlog == 1);

    auto stmt = test_db.prepare("INSERT INTO tbl1 VALUES(?)");
    stmt.execute(23);
    stmt.execute(42);
    sqlur.barrier();

    sqlur._start_interval();

    CHECK(sqlur._undo.firstlog == 3);
  }
}
