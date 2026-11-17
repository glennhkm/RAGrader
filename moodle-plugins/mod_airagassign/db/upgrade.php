<?php
// This file is part of Moodle - http://moodle.org/
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
// along with Moodle.  If not, see <http://www.gnu.org/licenses/>.

/**
 * Upgrade steps for mod_airagassign.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Execute upgrade steps.
 *
 * @param int $oldversion Old plugin version
 * @return bool
 */
function xmldb_airagassign_upgrade($oldversion) {
    global $DB;

    $dbman = $DB->get_manager();

    if ($oldversion < 2025010101) {
        $table = new xmldb_table('airagassign');

        // Add opendate column if it does not yet exist.
        if (!$dbman->field_exists($table, 'opendate')) {
            $field = new xmldb_field('opendate', XMLDB_TYPE_INTEGER, '10', null, XMLDB_NOTNULL, null, '0', 'maximumgrade');
            $dbman->add_field($table, $field);
        }

        upgrade_mod_savepoint(true, 2025010101, 'airagassign');
    }

    // ── 2025010102: Human-in-the-loop grading columns ────────────────────────
    // airagassign_submissions: ai_grade, ai_feedback, graded_by, teacher_note
    // airagassign_answers:     ai_score, ai_feedback
    if ($oldversion < 2025010102) {
        $table = new xmldb_table('airagassign_submissions');

        $subfields = [
            // AI suggested grade — separate from the teacher-confirmed 'grade' column.
            new xmldb_field('ai_grade', XMLDB_TYPE_NUMBER, '10, 2', null,
                null, null, null, 'grade'),
            // AI suggested overall feedback.
            new xmldb_field('ai_feedback', XMLDB_TYPE_TEXT, null, null,
                null, null, null, 'ai_grade'),
            // Who confirmed the final grade: 'ai_confirmed', 'teacher', or NULL (legacy).
            new xmldb_field('graded_by', XMLDB_TYPE_CHAR, '20', null,
                null, null, null, 'ai_response'),
            // Optional internal teacher note (not shown to students).
            new xmldb_field('teacher_note', XMLDB_TYPE_TEXT, null, null,
                null, null, null, 'graded_by'),
        ];

        foreach ($subfields as $field) {
            if (!$dbman->field_exists($table, $field)) {
                $dbman->add_field($table, $field);
            }
        }

        $table2 = new xmldb_table('airagassign_answers');

        $ansfields = [
            // AI suggested per-question score.
            new xmldb_field('ai_score', XMLDB_TYPE_NUMBER, '10, 2', null,
                null, null, null, 'score'),
            // AI suggested per-question feedback.
            new xmldb_field('ai_feedback', XMLDB_TYPE_TEXT, null, null,
                null, null, null, 'ai_score'),
        ];

        foreach ($ansfields as $field) {
            if (!$dbman->field_exists($table2, $field)) {
                $dbman->add_field($table2, $field);
            }
        }

        upgrade_mod_savepoint(true, 2025010102, 'airagassign');
    }

    // ── 2025010103: Dynamic schema self-healing for missing columns ──────────
    if ($oldversion < 2025010103) {
        $table = new xmldb_table('airagassign_submissions');

        $subfields = [
            // AI suggested grade — separate from the teacher-confirmed 'grade' column.
            new xmldb_field('ai_grade', XMLDB_TYPE_NUMBER, '10, 2', null,
                null, null, null, 'grade'),
            // AI suggested overall feedback.
            new xmldb_field('ai_feedback', XMLDB_TYPE_TEXT, null, null,
                null, null, null, 'ai_grade'),
            // Who confirmed the final grade: 'ai_confirmed', 'teacher', or NULL (legacy).
            new xmldb_field('graded_by', XMLDB_TYPE_CHAR, '20', null,
                null, null, null, 'ai_response'),
            // Optional internal teacher note (not shown to students).
            new xmldb_field('teacher_note', XMLDB_TYPE_TEXT, null, null,
                null, null, null, 'graded_by'),
        ];

        foreach ($subfields as $field) {
            if (!$dbman->field_exists($table, $field)) {
                $dbman->add_field($table, $field);
            }
        }

        $table2 = new xmldb_table('airagassign_answers');

        $ansfields = [
            // AI suggested per-question score.
            new xmldb_field('ai_score', XMLDB_TYPE_NUMBER, '10, 2', null,
                null, null, null, 'score'),
            // AI suggested per-question feedback.
            new xmldb_field('ai_feedback', XMLDB_TYPE_TEXT, null, null,
                null, null, null, 'ai_score'),
        ];

        foreach ($ansfields as $field) {
            if (!$dbman->field_exists($table2, $field)) {
                $dbman->add_field($table2, $field);
            }
        }

        upgrade_mod_savepoint(true, 2025010103, 'airagassign');
    }

    if ($oldversion < 2025010104) {
        $table = new xmldb_table('airagassign');
        $field = new xmldb_field('rubricmode', XMLDB_TYPE_CHAR, '20', null, XMLDB_NOTNULL, null, 'custom', 'allowlate');

        if (!$dbman->field_exists($table, $field)) {
            $dbman->add_field($table, $field);
        }

        upgrade_mod_savepoint(true, 2025010104, 'airagassign');
    }

    // Store background grading progress and failures so task errors are visible
    // after the teacher is redirected back to the assignment page.
    if ($oldversion < 2026071902) {
        $table = new xmldb_table('airagassign_submissions');
        $fields = [
            new xmldb_field('grading_error', XMLDB_TYPE_TEXT, null, null,
                null, null, null, 'confidence'),
            new xmldb_field('grading_requestid', XMLDB_TYPE_CHAR, '64', null,
                null, null, null, 'grading_error'),
            new xmldb_field('grading_started_at', XMLDB_TYPE_INTEGER, '10', null,
                XMLDB_NOTNULL, null, '0', 'grading_requestid'),
        ];

        foreach ($fields as $field) {
            if (!$dbman->field_exists($table, $field)) {
                $dbman->add_field($table, $field);
            }
        }

        // An interrupted task from an older plugin version can otherwise leave
        // a submission spinning forever with no task left to process it.
        $DB->execute("UPDATE {airagassign_submissions}
                         SET status = 'grading_failed',
                             grading_error = :error,
                             grading_started_at = 0
                       WHERE status = 'grading'", [
            'error' => 'Previous grading attempt was interrupted during the plugin upgrade. Please retry.',
        ]);

        upgrade_mod_savepoint(true, 2026071902, 'airagassign');
    }

    return true;
}
