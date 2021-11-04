pub mod undo {

    use fallible_iterator::FallibleIterator;
    use rusqlite::{Connection, Result};

    pub struct SQLiteUndoRedo<'c> {
        db: &'c Connection,
        _undo: Undo,
    }

    impl SQLiteUndoRedo<'_> {
        pub fn new(conn: &Connection) -> SQLiteUndoRedo {
            SQLiteUndoRedo {
                db: conn,
                _undo: Undo::new(),
            }
        }

        /// Start up the undo/redo system
        ///
        /// Arguments should be one or more database tables (in the database associated
        /// with the handle "db") whose changes are to be recorded for undo/redo
        /// purposes.
        ///
        pub fn activate(&mut self, args: &[&str]) -> Result<()> {
            if self._undo.active {
                return Ok(());
            }
            _create_triggers(self.db, args)?;
            self._undo.undostack = Vec::new();
            self._undo.redostack = Vec::new();
            self._undo.active = true;
            self._undo.freeze = Some(-1);
            self._start_interval()?;

            Ok(())
        }

        /// Halt the undo/redo system and delete the undo/redo stacks
        ///
        pub fn deactivate(&mut self) -> Result<()> {
            if !self._undo.active {
                return Ok(());
            }
            _drop_triggers(self.db)?;
            self._undo.undostack = Vec::new();
            self._undo.redostack = Vec::new();
            self._undo.active = false;
            self._undo.freeze = Some(-1);

            Ok(())
        }

        /// Stop accepting database changes into the undo stack
        ///
        /// From the point when this routine is called up until the next unfreeze,
        /// new database changes are rejected from the undo stack.
        ///
        pub fn freeze(&mut self) -> Result<()> {
            if self._undo.freeze.is_none() {
                return Ok(());
            }
            if self._undo.freeze >= Some(0) {
                println!("recursive call to ::undo::freeze");
                return Ok(());
            }
            self._undo.freeze =
                self.db
                    .query_row("SELECT coalesce(max(seq),0) FROM undolog", [], |row| {
                        row.get(0)
                    })?;

            Ok(())
        }

        /// Begin accepting undo actions again.
        ///
        pub fn unfreeze(&mut self) -> Result<()> {
            if self._undo.freeze.is_none() {
                return Ok(());
            }
            if self._undo.freeze < Some(0) {
                println!("called ::undo::unfreeze while not frozen");
                return Ok(());
            }
            self.db.execute(
                &("DELETE FROM undolog WHERE seq>".to_owned()
                    + &self._undo.freeze.unwrap().to_string()),
                [],
            )?;
            self._undo.freeze = Some(-1);

            Ok(())
        }

        /// Something undoable has happened
        ///
        /// This routine is called whenever an undoable action occurs.  Arrangements
        /// are made to invoke ::undo::barrier no later than the next idle moment.
        ///
        pub fn event(self) {
            if self._undo.pending == [] {
                // set _undo(pending) after idle ::undo::barrier
            }
        }

        /// Create an undo barrier right now.
        ///
        pub fn barrier(&mut self) -> Result<()> {
            // catch {after cancel $_undo(pending)}
            self._undo.pending = Vec::new();
            if !self._undo.active {
                // self.refresh();
                return Ok(());
            }
            let mut end =
                self.db
                    .query_row("SELECT coalesce(max(seq),0) FROM undolog", [], |row| {
                        row.get(0)
                    })?;
            if self._undo.freeze >= Some(0) && Some(end) > self._undo.freeze {
                end = self._undo.freeze.unwrap();
            }
            let begin = self._undo.firstlog;
            self._start_interval()?;
            if begin == self._undo.firstlog {
                // self.refresh();
                return Ok(());
            }
            self._undo.undostack.push((begin, end));
            self._undo.redostack = Vec::new();
            // self.refresh();

            Ok(())
        }

        /// Do a single step of undo
        ///
        pub fn undo(&mut self) -> Result<()> {
            self._step("undostack", "redostack")?;

            Ok(())
        }

        /// Redo a single step
        ///
        pub fn redo(&mut self) -> Result<()> {
            self._step("redostack", "undostack")?;

            Ok(())
        }

        /// Update the status of controls after a database change
        ///
        /// The undo module calls this routine after any undo/redo in order to
        /// cause controls gray out appropriately depending on the current state
        /// of the database.  This routine works by invoking the status_refresh
        /// module in all top-level namespaces.
        ///
        pub fn refresh(&self) {
            // set body {}
            // foreach ns namespace children :: {
            //   if {info proc ${ns}::status_refresh==""} continue
            //   append body ${ns}::status_refresh\n
            // }
            // proc ::undo::refresh {} $body
            // refresh
        }

        /// Redraw everything based on the current database
        ///
        /// The undo module calls this routine after any undo/redo in order to
        /// cause the screen to be completely redrawn based on the current database
        /// contents.  This is accomplished by calling the "reload" module in
        /// every top-level namespace other than ::undo.
        ///
        pub fn reload_all(&self) {
            // set body {}
            // foreach ns namespace children :: {
            //   if {info proc ${ns}::reload==""} continue
            //   append body ${ns}::reload\n
            // }
            // proc ::undo::reload_all {} $body
            // reload_all
        }
    }

    /// state information
    ///
    struct Undo {
        active: bool,
        undostack: Vec<(i32, i32)>,
        redostack: Vec<(i32, i32)>,
        pending: Vec<i32>,
        firstlog: i32,
        #[allow(dead_code)]
        startstate: Vec<i32>,

        freeze: Option<i32>,
    }

    impl Undo {
        fn new() -> Self {
            Undo {
                active: false,
                undostack: Vec::new(),
                redostack: Vec::new(),
                pending: Vec::new(),
                firstlog: 1,
                startstate: Vec::new(),

                freeze: None,
            }
        }
    }

    impl SQLiteUndoRedo<'_> {
        #[allow(dead_code)]
        /// Enable and/or disable menu options a buttons
        ///
        fn status_refresh(self) {
            if !self._undo.active || self._undo.undostack.len() == 0 {
                // .mb.edit entryconfig Undo -state disabled
                // .bb.undo config -state disabled
            } else {
                // .mb.edit entryconfig Undo -state normal
                // .bb.undo config -state normal
            }
            if !self._undo.active || self._undo.redostack.len() == 0 {
                // .mb.edit entryconfig Redo -state disabled
                // .bb.redo config -state disabled
            } else {
                // .mb.edit entryconfig Redo -state normal
                // .bb.redo config -state normal
            }
        }
    }

    /// Create change recording triggers for all tables listed
    ///
    /// Create a temporary table in the database named "undolog".  Create
    /// triggers that fire on any insert, delete, or update of TABLE1, TABLE2, ....
    /// When those triggers fire, insert records in undolog that contain
    /// SQL text for statements that will undo the insert, delete, or update.
    ///
    fn _create_triggers(db: &Connection, args: &[&str]) -> Result<()> {
        db.execute("DROP TABLE undolog", []).ok();
        db.execute(
            "CREATE TEMP TABLE undolog(seq integer primary key, sql text)",
            [],
        )?;
        for tbl in args {
            let mut stmt = db.prepare(&("pragma table_info(".to_owned() + tbl + ")"))?;
            let collist: Vec<(i32, String, String, bool, Option<String>, i32)> = stmt
                .query([])?
                .map(|row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                    ))
                })
                .collect()?;

            let mut sql = "CREATE TEMP TRIGGER _".to_owned()
                + tbl
                + "_it AFTER INSERT ON "
                + tbl
                + " BEGIN\n";
            sql += "  INSERT INTO undolog VALUES(NULL,";
            sql += &("'DELETE FROM ".to_owned() + tbl + " WHERE rowid='||new.rowid);\nEND;\n");

            sql += &("CREATE TEMP TRIGGER _".to_owned()
                + tbl
                + "_ut AFTER UPDATE ON "
                + tbl
                + " BEGIN\n");
            sql += "  INSERT INTO undolog VALUES(NULL,";
            sql += &("'UPDATE ".to_owned() + tbl + " ");
            let mut sep = "SET ";
            for (_x1, name, _x2, _x3, _x4, _x5) in &collist {
                sql += &(sep.to_owned() + name + "='||quote(old." + name + ")||'");
                sep = ",";
            }
            sql += " WHERE rowid='||old.rowid);\nEND;\n";

            sql += &("CREATE TEMP TRIGGER _".to_owned()
                + tbl
                + "_dt BEFORE DELETE ON "
                + tbl
                + " BEGIN\n");
            sql += "  INSERT INTO undolog VALUES(NULL,";
            sql += &("'INSERT INTO ".to_owned() + tbl + "(rowid");
            for (_x1, name, _x2, _x3, _x4, _x5) in &collist {
                sql += &(",".to_owned() + name);
            }
            sql += ") VALUES('||old.rowid||'";
            for (_x1, name, _x2, _x3, _x4, _x5) in &collist {
                sql += &(",'||quote(old.".to_owned() + name + ")||'");
            }
            sql += ")');\nEND;\n";

            db.execute_batch(&sql)?;
        }

        Ok(())
    }

    /// Drop all of the triggers that _create_triggers created
    ///
    fn _drop_triggers(db: &Connection) -> Result<()> {
        let mut stmt = db.prepare("SELECT name FROM sqlite_temp_schema WHERE type='trigger'")?;
        let tlist: Vec<String> = stmt.query([])?.map(|row| Ok(row.get(0)?)).collect()?;
        for trigger in &tlist {
            // if {!regexp {_.*_(i|u|d)t$} $trigger} continue
            db.execute(&("DROP TRIGGER ".to_owned() + trigger + ";"), [])?;
        }
        db.execute("DROP TABLE undolog", []).ok();

        Ok(())
    }

    impl SQLiteUndoRedo<'_> {
        /// Record the starting conditions of an undo interval
        ///
        fn _start_interval(&mut self) -> Result<()> {
            self._undo.firstlog =
                self.db
                    .query_row("SELECT coalesce(max(seq),0)+1 FROM undolog", [], |row| {
                        row.get(0)
                    })?;

            Ok(())
        }

        /// Do a single step of undo or redo
        ///
        /// For an undo V1=="undostack" and V2=="redostack".  For a redo,
        /// V1=="redostack" and V2=="undostack".
        ///
        fn _step(&mut self, v1: &str, v2: &str) -> Result<()> {
            let op = match v1 {
                "undostack" => &mut self._undo.undostack,
                "redostack" => &mut self._undo.redostack,
                _ => panic!(),
            }
            .pop()
            .unwrap();
            let (begin, end) = op;
            self.db.execute("BEGIN", [])?;
            let q1 = "SELECT sql FROM undolog WHERE seq>=".to_owned()
                + &begin.to_string()
                + " AND seq<="
                + &end.to_string()
                + " ORDER BY seq DESC";
            let mut stmt = self.db.prepare(&q1)?;
            let sqllist: Vec<String> = stmt.query([])?.map(|row| Ok(row.get(0)?)).collect()?;
            self.db.execute(
                &("DELETE FROM undolog WHERE seq>=".to_owned()
                    + &begin.to_string()
                    + " AND seq<="
                    + &end.to_string()),
                [],
            )?;
            self._undo.firstlog =
                self.db
                    .query_row("SELECT coalesce(max(seq),0)+1 FROM undolog", [], |row| {
                        row.get(0)
                    })?;
            for sql in sqllist {
                self.db.execute(&sql, [])?;
            }
            self.db.execute("COMMIT", [])?;
            // self.reload_all();

            let end = self
                .db
                .query_row("SELECT coalesce(max(seq),0) FROM undolog", [], |row| {
                    row.get(0)
                })?;
            let begin = self._undo.firstlog;
            match v2 {
                "undostack" => &mut self._undo.undostack,
                "redostack" => &mut self._undo.redostack,
                _ => panic!(),
            }
            .push((begin, end));
            self._start_interval()?;
            // self.refresh();

            Ok(())
        }
    }

    #[cfg(test)]
    mod tests {
        use rusqlite::{Connection, Result};

        use crate::undo::*;

        fn setup_connection() -> Result<Connection> {
            let conn = Connection::open_in_memory()?;

            conn.execute("CREATE TABLE tbl1(a)", [])?;
            conn.execute("CREATE TABLE tbl2(b)", [])?;

            Ok(conn)
        }

        #[test]
        fn test_activate_one_table() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;

            assert_eq!(sqlur._undo.undostack, []);
            assert_eq!(sqlur._undo.redostack, []);
            assert_eq!(sqlur._undo.active, true);
            assert_eq!(sqlur._undo.freeze, Some(-1));

            Ok(())
        }

        #[test]
        fn test_activate_several_tables() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1", "tbl2"])?;

            assert_eq!(sqlur._undo.undostack, []);
            assert_eq!(sqlur._undo.redostack, []);
            assert_eq!(sqlur._undo.active, true);
            assert_eq!(sqlur._undo.freeze, Some(-1));

            Ok(())
        }

        #[test]
        fn test_activate_while_active() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            assert_eq!(sqlur._undo.active, false);
            sqlur.activate(&["tbl1"])?;
            assert_eq!(sqlur._undo.active, true);

            sqlur.activate(&["tbl1"])?;

            assert_eq!(sqlur._undo.active, true);

            Ok(())
        }

        #[test]
        fn test_deactivate() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;

            sqlur.deactivate()?;

            assert_eq!(sqlur._undo.undostack, []);
            assert_eq!(sqlur._undo.redostack, []);
            assert_eq!(sqlur._undo.active, false);
            assert_eq!(sqlur._undo.freeze, Some(-1));

            Ok(())
        }

        #[test]
        fn test_deactivate_while_not_active() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            assert_eq!(sqlur._undo.active, false);

            sqlur.deactivate()?;

            Ok(())
        }

        #[test]
        fn test_freeze() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            assert_eq!(sqlur._undo.freeze, Some(-1));

            let mut stmt = conn.prepare("INSERT INTO tbl1 VALUES(?)")?;
            stmt.execute([23])?;
            stmt.execute([42])?;
            sqlur.barrier()?;

            sqlur.freeze()?;

            assert_eq!(sqlur._undo.freeze, Some(2));

            Ok(())
        }

        #[test]
        fn test_freeze_while_frozen() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            assert_eq!(sqlur._undo.freeze, Some(-1));

            sqlur.freeze()?;

            assert_eq!(sqlur._undo.freeze, Some(0));

            sqlur.freeze()?;

            Ok(())
        }

        fn _select_to_vec(conn: &Connection, table: &str) -> Vec<i32> {
            return conn
                .prepare(&("SELECT * from ".to_owned() + table))
                .unwrap()
                .query([])
                .unwrap()
                .map(|row| Ok(row.get(0)?))
                .collect::<Vec<i32>>()
                .unwrap();
        }

        #[test]
        fn test_unfreeze() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            assert_eq!(sqlur._undo.freeze, Some(-1));

            let mut stmt = conn.prepare("INSERT INTO tbl1 VALUES(?)")?;
            stmt.execute([23])?;
            stmt.execute([42])?;
            sqlur.barrier()?;

            sqlur.freeze()?;
            assert_eq!(sqlur._undo.freeze, Some(2));

            stmt.execute([69])?;
            stmt.execute([404])?;
            sqlur.barrier()?;

            assert_eq!(_select_to_vec(&conn, "undolog").len(), 4);

            sqlur.unfreeze()?;

            assert_eq!(_select_to_vec(&conn, "undolog").len(), 2);

            assert_eq!(sqlur._undo.freeze, Some(-1));

            Ok(())
        }

        #[test]
        fn test_unfreeze_while_not_frozen() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            assert_eq!(sqlur._undo.freeze, Some(-1));

            sqlur.unfreeze()?;

            Ok(())
        }

        #[test]
        fn test_barrier() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;

            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            assert_eq!(sqlur._undo.undostack, [(1, 1)]);
            conn.execute("INSERT INTO tbl1 VALUES(?)", [42])?;

            sqlur.barrier()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1), (2, 2)]);

            Ok(())
        }

        #[test]
        fn test_barrier_several_changes() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;

            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [42])?;

            sqlur.barrier()?;

            assert_eq!(sqlur._undo.undostack, [(1, 2)]);

            Ok(())
        }

        #[test]
        fn test_barrier_while_frozen() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;

            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            sqlur.freeze()?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [42])?;

            sqlur.barrier()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1), (2, 1)]);

            Ok(())
        }

        #[test]
        fn test_barrier_after_no_changes() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;

            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            assert_eq!(sqlur._undo.undostack, [(1, 1)]);

            sqlur.barrier()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1)]);

            Ok(())
        }

        #[test]
        fn test_undo_insert() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), [23]);

            sqlur.undo()?;

            assert_eq!(sqlur._undo.undostack, []);
            assert_eq!(sqlur._undo.redostack, [(1, 1)]);
            assert_eq!(sqlur._undo.firstlog, 2);
            assert_eq!(_select_to_vec(&conn, "tbl1"), []);

            Ok(())
        }

        #[test]
        fn test_undo_update() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            conn.execute("UPDATE tbl1 SET a=? WHERE a=?", [42, 23])?;
            sqlur.barrier()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), [42]);

            sqlur.undo()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1)]);
            assert_eq!(sqlur._undo.redostack, [(2, 2)]);
            assert_eq!(sqlur._undo.firstlog, 3);
            assert_eq!(_select_to_vec(&conn, "tbl1"), [23]);

            Ok(())
        }

        #[test]
        fn test_undo_delete() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            conn.execute("DELETE FROM tbl1 WHERE a=?", [23])?;
            sqlur.barrier()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), []);

            sqlur.undo()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1)]);
            assert_eq!(sqlur._undo.redostack, [(2, 2)]);
            assert_eq!(sqlur._undo.firstlog, 3);
            assert_eq!(_select_to_vec(&conn, "tbl1"), [23]);

            Ok(())
        }

        #[test]
        fn test_undo_several_changes() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [42])?;
            conn.execute("UPDATE tbl1 SET a=? WHERE a=?", [69, 42])?;
            conn.execute("DELETE FROM tbl1 WHERE a=?", [23])?;
            sqlur.barrier()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), [69]);

            sqlur.undo()?;

            assert_eq!(sqlur._undo.undostack, []);
            assert_eq!(sqlur._undo.redostack, [(1, 4)]);
            assert_eq!(sqlur._undo.firstlog, 5);
            assert_eq!(_select_to_vec(&conn, "tbl1"), []);

            Ok(())
        }

        #[test]
        fn test_redo_insert() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            sqlur.undo()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), []);

            sqlur.redo()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1)]);
            assert_eq!(sqlur._undo.redostack, []);
            assert_eq!(sqlur._undo.firstlog, 2);
            assert_eq!(_select_to_vec(&conn, "tbl1"), [23]);

            Ok(())
        }

        #[test]
        fn test_redo_update() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            conn.execute("UPDATE tbl1 SET a=? WHERE a=?", [42, 23])?;
            sqlur.barrier()?;
            sqlur.undo()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), [23]);

            sqlur.redo()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1), (2, 2)]);
            assert_eq!(sqlur._undo.redostack, []);
            assert_eq!(sqlur._undo.firstlog, 3);
            assert_eq!(_select_to_vec(&conn, "tbl1"), [42]);

            Ok(())
        }

        #[test]
        fn test_redo_delete() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            sqlur.barrier()?;
            conn.execute("DELETE FROM tbl1 WHERE a=?", [23])?;
            sqlur.barrier()?;
            sqlur.undo()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), [23]);

            sqlur.redo()?;

            assert_eq!(sqlur._undo.undostack, [(1, 1), (2, 2)]);
            assert_eq!(sqlur._undo.redostack, []);
            assert_eq!(sqlur._undo.firstlog, 3);
            assert_eq!(_select_to_vec(&conn, "tbl1"), []);

            Ok(())
        }

        #[test]
        fn test_redo_several_changes() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [23])?;
            conn.execute("INSERT INTO tbl1 VALUES(?)", [42])?;
            conn.execute("UPDATE tbl1 SET a=? WHERE a=?", [69, 42])?;
            conn.execute("DELETE FROM tbl1 WHERE a=?", [23])?;
            sqlur.barrier()?;
            sqlur.undo()?;

            assert_eq!(_select_to_vec(&conn, "tbl1"), []);

            sqlur.redo()?;

            assert_eq!(sqlur._undo.undostack, [(1, 4)]);
            assert_eq!(sqlur._undo.redostack, []);
            assert_eq!(sqlur._undo.firstlog, 5);
            assert_eq!(_select_to_vec(&conn, "tbl1"), [69]);

            Ok(())
        }

        #[test]
        fn test_create_triggers_no_tables() -> Result<()> {
            let conn = setup_connection()?;

            _create_triggers(&conn, &[])?;

            Ok(())
        }

        #[test]
        fn test_create_triggers_one_table() -> Result<()> {
            let conn = setup_connection()?;

            _create_triggers(&conn, &["tbl1"])?;

            Ok(())
        }

        #[test]
        fn test_create_triggers_several_tables() -> Result<()> {
            let conn = setup_connection()?;

            _create_triggers(&conn, &["tbl1", "tbl2"])?;

            Ok(())
        }

        #[test]
        fn test_drop_triggers() -> Result<()> {
            let conn = setup_connection()?;

            _create_triggers(&conn, &["tbl1", "tbl2"])?;

            _drop_triggers(&conn)?;

            Ok(())
        }

        #[test]
        fn test_start_interval() -> Result<()> {
            let conn = setup_connection()?;
            let mut sqlur = SQLiteUndoRedo::new(&conn);

            sqlur.activate(&["tbl1"])?;

            sqlur._start_interval()?;

            assert_eq!(sqlur._undo.firstlog, 1);

            let mut stmt = conn.prepare("INSERT INTO tbl1 VALUES(?)")?;
            stmt.execute([23])?;
            stmt.execute([42])?;
            sqlur.barrier()?;

            sqlur._start_interval()?;

            assert_eq!(sqlur._undo.firstlog, 3);

            Ok(())
        }
    }
}
