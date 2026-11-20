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
 * Library of interface functions and constants for AI RAG Assignment module.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

use mod_airagassign\local\material_scope;
use mod_airagassign\local\rubric_builder;

/**
 * Returns the features supported by this module.
 *
 * @param string $feature FEATURE_xx constant
 * @return mixed True if supported, null if unknown
 */
function airagassign_supports($feature) {
    switch ($feature) {
        case FEATURE_MOD_INTRO:
            return true;
        case FEATURE_SHOW_DESCRIPTION:
            return true;
        case FEATURE_GRADE_HAS_GRADE:
            return true;
        case FEATURE_BACKUP_MOODLE2:
            return true;
        case FEATURE_ADVANCED_GRADING:
            return true;
        case FEATURE_MOD_PURPOSE:
            return MOD_PURPOSE_ASSESSMENT;
        default:
            return null;
    }
}

/**
 * Decode the dynamic table fields serialised as JSON by the form's JavaScript.
 *
 * These are invisible to moodleform::get_data() but are passed via registered
 * hidden fields serialised by JS on submit.
 *
 * @param stdClass $data Form data, updated in place
 */
function airagassign_decode_dynamic_fields(stdClass $data): void {
    if (!empty($data->criteria_json)) {
        $decoded = json_decode($data->criteria_json, true);
        if (is_array($decoded)) {
            $data->criterionname     = array_column($decoded, 'name');
            $data->criteriondesc     = array_column($decoded, 'desc');
            $data->criterionmaxscore = array_column($decoded, 'maxscore');
        }
    }
    if (!empty($data->questions_json)) {
        $decoded = json_decode($data->questions_json, true);
        if (is_array($decoded)) {
            $data->questions = $decoded;
        }
    }
}

/**
 * Insert the questions (quiz mode), custom criteria and linked materials of an instance.
 *
 * @param stdClass $data Form data with id set
 */
function airagassign_save_children(stdClass $data): void {
    global $DB;

    if ($data->assignmode === 'quiz' && !empty($data->questions)) {
        foreach ($data->questions as $i => $qtext) {
            $qtext = trim($qtext);
            if ($qtext === '') {
                continue;
            }
            $DB->insert_record('airagassign_questions', (object)[
                'assignid' => $data->id,
                'questiontext' => $qtext,
                'sortorder' => $i,
                'timecreated' => time(),
            ]);
        }
    }

    if (($data->rubricmode ?? '') === 'custom' && !empty($data->criterionname)) {
        foreach ($data->criterionname as $i => $cname) {
            $cname = trim($cname);
            if ($cname === '') {
                continue;
            }
            $DB->insert_record('airagassign_criteria', (object)[
                'assignid' => $data->id,
                'name' => $cname,
                'description' => $data->criteriondesc[$i] ?? '',
                'maxscore' => $data->criterionmaxscore[$i] ?? 100,
                'sortorder' => $i,
            ]);
        }
    }

    if (!empty($data->materials)) {
        foreach ($data->materials as $materialid) {
            $DB->insert_record('airagassign_materials', (object)[
                'assignid' => $data->id,
                'materialid' => $materialid,
            ]);
        }
    }
}

/**
 * Save the manual reference file draft area.
 *
 * @param stdClass $data Form data with manualfile set
 * @param context_module $context Module context
 */
function airagassign_save_manual_file(stdClass $data, context_module $context): void {
    file_save_draft_area_files($data->manualfile, $context->id, 'mod_airagassign', 'manualfile', 0,
        ['subdirs' => false, 'maxfiles' => 1]);
}

/**
 * Add a new AI RAG Assignment instance.
 *
 * @param stdClass $data Form data
 * @param mod_airagassign_mod_form $mform The form
 * @return int The new instance id
 */
function airagassign_add_instance($data, $mform = null) {
    global $DB;

    airagassign_decode_dynamic_fields($data);
    $data->timecreated = time();
    $data->timemodified = time();
    $data->id = $DB->insert_record('airagassign', $data);
    airagassign_save_children($data);

    // Save the manual file; vectorization runs in a background task.
    $context = context_module::instance($data->coursemodule);
    if (isset($data->manualfile)) {
        airagassign_save_manual_file($data, $context);
        material_scope::sync_manualfiles((int)$data->id, (int)$data->course, (int)$context->id);
    }

    airagassign_grade_item_update($data);
    rubric_builder::sync_moodle($data);

    return $data->id;
}

/**
 * Update an existing AI RAG Assignment instance.
 *
 * @param stdClass $data Form data
 * @param mod_airagassign_mod_form $mform The form
 * @return bool True on success
 */
function airagassign_update_instance($data, $mform = null) {
    global $DB;

    airagassign_decode_dynamic_fields($data);
    $data->timemodified = time();
    $data->id = $data->instance;
    $DB->update_record('airagassign', $data);

    // Re-save questions, rubric criteria and linked materials.
    $DB->delete_records('airagassign_questions', ['assignid' => $data->id]);
    $DB->delete_records('airagassign_criteria', ['assignid' => $data->id]);
    $DB->delete_records('airagassign_materials', ['assignid' => $data->id]);
    airagassign_save_children($data);

    // Re-save the manual file: removed files lose their (owner-scoped) vectors,
    // new or replaced files are re-vectorized in a background task.
    $context = context_module::instance($data->coursemodule);
    if (isset($data->manualfile)) {
        $oldnames = array_keys(material_scope::manual_file_hashes($context->id));
        airagassign_save_manual_file($data, $context);
        material_scope::sync_manualfiles((int)$data->id, (int)$data->course, (int)$context->id, $oldnames);
    }

    airagassign_grade_item_update($data);
    rubric_builder::sync_moodle($data);

    return true;
}

/**
 * Delete an AI RAG Assignment instance.
 *
 * @param int $id Instance ID
 * @return bool True on success
 */
function airagassign_delete_instance($id) {
    global $DB;

    $assign = $DB->get_record('airagassign', ['id' => $id]);
    if (!$assign) {
        return false;
    }

    // Remove the manual files' vectors (owner airagassign:{id}) and status rows first.
    $cm = get_coursemodule_from_instance('airagassign', $id, 0, false, IGNORE_MISSING);
    $context = $cm ? context_module::instance($cm->id, IGNORE_MISSING) : false;
    material_scope::delete_all_manualfiles($assign, $context ? (int)$context->id : null);

    // Delete answers for all submissions.
    $submissions = $DB->get_records('airagassign_submissions', ['assignid' => $id], '', 'id');
    foreach ($submissions as $sub) {
        $DB->delete_records('airagassign_answers', ['submissionid' => $sub->id]);
    }

    $DB->delete_records('airagassign_submissions', ['assignid' => $id]);
    $DB->delete_records('airagassign_questions', ['assignid' => $id]);
    $DB->delete_records('airagassign_criteria', ['assignid' => $id]);
    $DB->delete_records('airagassign_materials', ['assignid' => $id]);
    $DB->delete_records('airagassign', ['id' => $id]);

    // Remove grade item.
    airagassign_grade_item_delete($assign);

    return true;
}

/**
 * Create/update grade item in gradebook.
 *
 * @param stdClass $assign The assignment instance
 * @param mixed $grades Optional grade data
 * @return int
 */
function airagassign_grade_item_update($assign, $grades = null) {
    global $CFG;
    require_once($CFG->libdir . '/gradelib.php');

    $params = [
        'itemname' => $assign->name,
        'gradetype' => GRADE_TYPE_VALUE,
        'grademax' => $assign->maximumgrade,
        'grademin' => 0,
    ];

    if ($grades === 'reset') {
        $params['reset'] = true;
        $grades = null;
    }

    return grade_update('mod/airagassign', $assign->course, 'mod', 'airagassign', $assign->id, 0, $grades, $params);
}

/**
 * Delete grade item from gradebook.
 *
 * @param stdClass $assign The assignment instance
 * @return int
 */
function airagassign_grade_item_delete($assign) {
    global $CFG;
    require_once($CFG->libdir . '/gradelib.php');

    return grade_update('mod/airagassign', $assign->course, 'mod', 'airagassign', $assign->id, 0, null, ['deleted' => 1]);
}

/**
 * Update grades in gradebook.
 *
 * @param stdClass $assign The assignment instance
 * @param int $userid User ID (0 for all)
 * @param bool $nullifnone Set to null if no grade
 */
function airagassign_update_grades($assign, $userid = 0, $nullifnone = true) {
    global $CFG, $DB;
    require_once($CFG->libdir . '/gradelib.php');

    if ($userid) {
        $submissions = $DB->get_records('airagassign_submissions', [
            'assignid' => $assign->id,
            'userid' => $userid,
            'status' => 'graded',
        ]);
    } else {
        $submissions = $DB->get_records('airagassign_submissions', [
            'assignid' => $assign->id,
            'status' => 'graded',
        ]);
    }

    $grades = [];
    foreach ($submissions as $sub) {
        $grade = new stdClass();
        $grade->userid = $sub->userid;
        $grade->rawgrade = $sub->grade;
        $grade->dategraded = $sub->timegraded;
        $grade->datesubmitted = $sub->timecreated;
        $grades[$sub->userid] = $grade;
    }

    if (empty($grades) && $nullifnone) {
        if ($userid) {
            $grade = new stdClass();
            $grade->userid = $userid;
            $grade->rawgrade = null;
            $grades[$userid] = $grade;
        }
    }

    airagassign_grade_item_update($assign, $grades);
}

/**
 * Get the list of uploaded manual files for an assignment instance.
 *
 * @param int $contextid The context ID
 * @return array List of stored_file objects
 */
function airagassign_get_uploaded_files($contextid) {
    return material_scope::manual_files((int)$contextid);
}

/**
 * Return the vector owner id of an assignment's manual reference files.
 *
 * @param int $assignid Assignment instance ID
 * @return string Owner id, e.g. "airagassign:7"
 */
function airagassign_manualfile_owner(int $assignid): string {
    return material_scope::manualfile_owner($assignid);
}

/**
 * Whether a submission has a stored AI confidence value (0 is a valid value).
 *
 * @param stdClass $submission Submission record
 * @return bool
 */
function airagassign_has_confidence($submission): bool {
    return isset($submission->confidence) && is_numeric($submission->confidence);
}

/**
 * Return view actions for participation report.
 *
 * @return array
 */
function airagassign_get_view_actions() {
    return ['view', 'view all'];
}

/**
 * Return post actions for participation report.
 *
 * @return array
 */
function airagassign_get_post_actions() {
    return ['submit', 'grade'];
}

/**
 * Serves the files from this plugin.
 *
 * @param stdClass $course
 * @param stdClass $cm
 * @param stdClass $context
 * @param string $filearea
 * @param array $args
 * @param bool $forcedownload
 * @param array $options
 * @return bool
 */
function airagassign_pluginfile($course, $cm, $context, $filearea, $args, $forcedownload, array $options = []) {
    if ($context->contextlevel != CONTEXT_MODULE) {
        return false;
    }

    require_course_login($course, true, $cm);

    if ($filearea !== 'manualfile') {
        return false;
    }

    $itemid = array_shift($args);
    $filename = array_pop($args);
    $filepath = $args ? '/' . implode('/', $args) . '/' : '/';

    $fs = get_file_storage();
    $file = $fs->get_file($context->id, 'mod_airagassign', $filearea, $itemid, $filepath, $filename);

    if (!$file) {
        return false;
    }

    send_stored_file($file, 0, 0, $forcedownload, $options);
}
