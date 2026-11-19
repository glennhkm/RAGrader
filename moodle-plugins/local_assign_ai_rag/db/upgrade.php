<?php
// This file is part of Moodle - https://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Moodle is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Moodle.  If not, see <https://www.gnu.org/licenses/>.

/**
 * Database upgrade steps for local_assign_ai_rag.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Upgrade the plugin database tables.
 *
 * @param int $oldversion The version we are upgrading from.
 * @return bool
 */
function xmldb_local_assign_ai_rag_upgrade($oldversion) {
    global $DB;

    $dbman = $DB->get_manager();

    if ($oldversion < 2025121803) {
        // Define table local_assign_ai_rag_rubric.
        $table = new xmldb_table('local_assign_ai_rag_rubric');

        // Adding fields.
        $table->add_field('id', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, XMLDB_SEQUENCE, null);
        $table->add_field('assignmentid', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, null, null);
        $table->add_field('rubric_json', XMLDB_TYPE_TEXT, null, null, XMLDB_NOTNULL, null, null);
        $table->add_field('max_grade', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, null, '100');
        $table->add_field('usermodified', XMLDB_TYPE_INTEGER, '10', null, null, null, null);
        $table->add_field('timecreated', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, null, '0');
        $table->add_field('timemodified', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, null, '0');

        // Adding keys.
        $table->add_key('primary', XMLDB_KEY_PRIMARY, ['id']);
        $table->add_key('rubric_assignment_uniq', XMLDB_KEY_UNIQUE, ['assignmentid']);
        $table->add_key('rubric_user_fk', XMLDB_KEY_FOREIGN, ['usermodified'], 'user', ['id']);

        // Conditionally create table.
        if (!$dbman->table_exists($table)) {
            $dbman->create_table($table);
        }

        // Savepoint.
        upgrade_plugin_savepoint(true, 2025121803, 'local', 'assign_ai_rag');
    }

    if ($oldversion < 2026071902) {
        $table = new xmldb_table('local_assign_ai_rag_pending');

        // 1. Store grades with the same precision as {assign_grades}.grade. The old
        //    integer column rounded AI grades and rejected decimal manual grades.
        $field = new xmldb_field('grade', XMLDB_TYPE_NUMBER, '10, 5', null, null, null, null, 'message');
        if ($dbman->field_exists($table, $field)) {
            $dbman->change_field_type($table, $field);
        }

        // 2. The grading observer wrote the non-canonical status 'approve'.
        $DB->set_field('local_assign_ai_rag_pending', 'status', 'approved', ['status' => 'approve']);

        // 3. Auto-grading used to insert a second pending row next to the one the
        //    submission observer creates. Keep only the most recent row per
        //    assignment/user so lookups by (assignmentid, userid) are unambiguous.
        // A recordset is used because get_records_sql() would key rows by the
        // first column and collapse different users of the same assignment.
        $duplicates = $DB->get_recordset_sql(
            "SELECT assignmentid, userid, MAX(id) AS keepid
               FROM {local_assign_ai_rag_pending}
           GROUP BY assignmentid, userid
             HAVING COUNT(1) > 1"
        );
        $groups = [];
        foreach ($duplicates as $duplicate) {
            $groups[] = $duplicate;
        }
        $duplicates->close();
        foreach ($groups as $duplicate) {
            $DB->delete_records_select(
                'local_assign_ai_rag_pending',
                'assignmentid = :assignmentid AND userid = :userid AND id <> :keepid',
                [
                    'assignmentid' => $duplicate->assignmentid,
                    'userid' => $duplicate->userid,
                    'keepid' => $duplicate->keepid,
                ]
            );
        }

        upgrade_plugin_savepoint(true, 2026071902, 'local', 'assign_ai_rag');
    }

    return true;
}
