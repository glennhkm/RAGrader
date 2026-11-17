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

    return true;
}
