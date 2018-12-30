# Copied from https://www.sqlite.org/undoredo.html


# Everything goes in a private namespace
namespace eval ::undo {

# proc:  ::undo::activate TABLE ...
# title: Start up the undo/redo system
#
# Arguments should be one or more database tables (in the database associated
# with the handle "db") whose changes are to be recorded for undo/redo
# purposes.
#
proc activate {args} {
  variable _undo
  if {$_undo(active)} return
  eval _create_triggers db $args
  set _undo(undostack) {}
  set _undo(redostack) {}
  set _undo(active) 1
  set _undo(freeze) -1
  _start_interval
}

# proc:  ::undo::deactivate
# title: Halt the undo/redo system and delete the undo/redo stacks
#
proc deactivate {} {
  variable _undo
  if {!$_undo(active)} return
  _drop_triggers db
  set _undo(undostack) {}
  set _undo(redostack) {}
  set _undo(active) 0
  set _undo(freeze) -1
}

# proc:  ::undo::freeze
# title: Stop accepting database changes into the undo stack
#
# From the point when this routine is called up until the next unfreeze,
# new database changes are rejected from the undo stack.
#
proc freeze {} {
  variable _undo
  if {!}; hd_resolve_one {info exists _undo(freeze)}; hd_puts {} return
  if {$_undo(freeze)>=0} {error "recursive call to ::undo::freeze"}
  set _undo(freeze) }; hd_resolve_one {db one {SELECT coalesce(max(seq),0) FROM undolog}}; hd_puts {
}

# proc:  ::undo::unfreeze
# title: Begin accepting undo actions again.
#
proc unfreeze {} {
  variable _undo
  if {!}; hd_resolve_one {info exists _undo(freeze)}; hd_puts {} return
  if {$_undo(freeze)<0} {error "called ::undo::unfreeze while not frozen"}
  db eval "DELETE FROM undolog WHERE seq>$_undo(freeze)"
  set _undo(freeze) -1
}

# proc:  ::undo::event
# title: Something undoable has happened
#
# This routine is called whenever an undoable action occurs.  Arrangements
# are made to invoke ::undo::barrier no later than the next idle moment.
#
proc event {} {
  variable _undo
  if {$_undo(pending)==""} {
    set _undo(pending) }; hd_resolve_one {after idle ::undo::barrier}; hd_puts {
  }
}

# proc:  ::undo::barrier
# title: Create an undo barrier right now.
#
proc barrier {} {
  variable _undo
  catch {after cancel $_undo(pending)}
  set _undo(pending) {}
  if {!$_undo(active)} {
    refresh
    return
  }
  set end }; hd_resolve_one {db one {SELECT coalesce(max(seq),0) FROM undolog}}; hd_puts {
  if {$_undo(freeze)>=0 && $end>$_undo(freeze)} {set end $_undo(freeze)}
  set begin $_undo(firstlog)
  _start_interval
  if {$begin==$_undo(firstlog)} {
    refresh
    return
  }
  lappend _undo(undostack) }; hd_resolve_one {list $begin $end}; hd_puts {
  set _undo(redostack) {}
  refresh
}

# proc:  ::undo::undo
# title: Do a single step of undo
#
proc undo {} {
  _step undostack redostack
}

# proc:  ::undo::redo
# title: Redo a single step
#
proc redo {} {
  _step redostack undostack
}

# proc:   ::undo::refresh
# title:  Update the status of controls after a database change
#
# The undo module calls this routine after any undo/redo in order to
# cause controls gray out appropriately depending on the current state
# of the database.  This routine works by invoking the status_refresh
# module in all top-level namespaces.
#
proc refresh {} {
  set body {}
  foreach ns }; hd_resolve_one {namespace children ::}; hd_puts { {
    if {}; hd_resolve_one {info proc ${ns}::status_refresh}; hd_puts {==""} continue
    append body ${ns}::status_refresh\n
  }
  proc ::undo::refresh {} $body
  refresh
}

# proc:   ::undo::reload_all
# title:  Redraw everything based on the current database
#
# The undo module calls this routine after any undo/redo in order to
# cause the screen to be completely redrawn based on the current database
# contents.  This is accomplished by calling the "reload" module in
# every top-level namespace other than ::undo.
#
proc reload_all {} {
  set body {}
  foreach ns }; hd_resolve_one {namespace children ::}; hd_puts { {
    if {}; hd_resolve_one {info proc ${ns}::reload}; hd_puts {==""} continue
    append body ${ns}::reload\n
  }
  proc ::undo::reload_all {} $body
  reload_all
}

##############################################################################
# The public interface to this module is above.  Routines and variables that
# follow (and whose names begin with "_") are private to this module.
##############################################################################

# state information
#
set _undo(active) 0
set _undo(undostack) {}
set _undo(redostack) {}
set _undo(pending) {}
set _undo(firstlog) 1
set _undo(startstate) {}


# proc:  ::undo::status_refresh
# title: Enable and/or disable menu options a buttons
#
proc status_refresh {} {
  variable _undo
  if {!$_undo(active) || }; hd_resolve_one {llength $_undo(undostack)}; hd_puts {==0} {
    .mb.edit entryconfig Undo -state disabled
    .bb.undo config -state disabled
  } else {
    .mb.edit entryconfig Undo -state normal
    .bb.undo config -state normal
  }
  if {!$_undo(active) || }; hd_resolve_one {llength $_undo(redostack)}; hd_puts {==0} {
    .mb.edit entryconfig Redo -state disabled
    .bb.redo config -state disabled
  } else {
    .mb.edit entryconfig Redo -state normal
    .bb.redo config -state normal
  }
}

# xproc:  ::undo::_create_triggers DB TABLE1 TABLE2 ...
# title:  Create change recording triggers for all tables listed
#
# Create a temporary table in the database named "undolog".  Create
# triggers that fire on any insert, delete, or update of TABLE1, TABLE2, ....
# When those triggers fire, insert records in undolog that contain
# SQL text for statements that will undo the insert, delete, or update.
#
proc _create_triggers {db args} {
  catch {$db eval {DROP TABLE undolog}}
  $db eval {CREATE TEMP TABLE undolog(seq integer primary key, sql text)}
  foreach tbl $args {
    set collist }; hd_resolve_one {$db eval "pragma table_info($tbl)"}; hd_puts {
    set sql "CREATE TEMP TRIGGER _${tbl}_it AFTER INSERT ON $tbl BEGIN\n"
    append sql "  INSERT INTO undolog VALUES(NULL,"
    append sql "'DELETE FROM $tbl WHERE rowid='||new.rowid);\nEND;\n"

    append sql "CREATE TEMP TRIGGER _${tbl}_ut AFTER UPDATE ON $tbl BEGIN\n"
    append sql "  INSERT INTO undolog VALUES(NULL,"
    append sql "'UPDATE $tbl "
    set sep "SET "
    foreach {x1 name x2 x3 x4 x5} $collist {
      append sql "$sep$name='||quote(old.$name)||'"
      set sep ","
    }
    append sql " WHERE rowid='||old.rowid);\nEND;\n"

    append sql "CREATE TEMP TRIGGER _${tbl}_dt BEFORE DELETE ON $tbl BEGIN\n"
    append sql "  INSERT INTO undolog VALUES(NULL,"
    append sql "'INSERT INTO ${tbl}(rowid"
    foreach {x1 name x2 x3 x4 x5} $collist {append sql ,$name}
    append sql ") VALUES('||old.rowid||'"
    foreach {x1 name x2 x3 x4 x5} $collist {append sql ,'||quote(old.$name)||'}
    append sql ")');\nEND;\n"

    $db eval $sql
  }
}

# xproc:  ::undo::_drop_triggers DB
# title:  Drop all of the triggers that _create_triggers created
#
proc _drop_triggers {db} {
  set tlist }; hd_resolve_one {$db eval {SELECT name FROM sqlite_temp_master
                       WHERE type='trigger'}}; hd_puts {
  foreach trigger $tlist {
    if {!}; hd_resolve_one {regexp {_.*_(i|u|d)t$} $trigger}; hd_puts {} continue
    $db eval "DROP TRIGGER $trigger;"
  }
  catch {$db eval {DROP TABLE undolog}}
}

# xproc: ::undo::_start_interval
# title: Record the starting conditions of an undo interval
#
proc _start_interval {} {
  variable _undo
  set _undo(firstlog) }; hd_resolve_one {db one {SELECT coalesce(max(seq),0)+1 FROM undolog}}; hd_puts {
}

# xproc: ::undo::_step V1 V2
# title: Do a single step of undo or redo
#
# For an undo V1=="undostack" and V2=="redostack".  For a redo,
# V1=="redostack" and V2=="undostack".
#
proc _step {v1 v2} {
  variable _undo
  set op }; hd_resolve_one {lindex $_undo($v1) end}; hd_puts {
  set _undo($v1) }; hd_resolve_one {lrange $_undo($v1) 0 end-1}; hd_puts {
  foreach {begin end} $op break
  db eval BEGIN
  set q1 "SELECT sql FROM undolog WHERE seq>=$begin AND seq<=$end
          ORDER BY seq DESC"
  set sqllist }; hd_resolve_one {db eval $q1}; hd_puts {
  db eval "DELETE FROM undolog WHERE seq>=$begin AND seq<=$end"
  set _undo(firstlog) }; hd_resolve_one {db one {SELECT coalesce(max(seq),0)+1 FROM undolog}}; hd_puts {
  foreach sql $sqllist {
    db eval $sql
  }
  db eval COMMIT
  reload_all

  set end }; hd_resolve_one {db one {SELECT coalesce(max(seq),0) FROM undolog}}; hd_puts {
  set begin $_undo(firstlog)
  lappend _undo($v2) }; hd_resolve_one {list $begin $end}; hd_puts {
  _start_interval
  refresh
}


# End of the ::undo namespace
}
