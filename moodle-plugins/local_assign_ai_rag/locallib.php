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
 * Local library functions for local_assign_ai_rag.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/grade/grading/lib.php');

/**
 * Converts the assignment rubric into simplified JSON for RAG AI.
 *
 * @param assign $assign The assignment instance.
 * @return array|null Simplified rubric array or null if no rubric is active.
 * @package local_assign_ai_rag
 */
function local_assign_ai_rag_build_rubric_json(assign $assign) {
    global $DB;

    $context = $assign->get_context();

    // Initialize grading manager.
    $gradingmanager = get_grading_manager($context, 'mod_assign', 'submissions');
    $method = $gradingmanager->get_active_method();

    if ($method !== 'rubric') {
        return null;
    }

    $controller = $gradingmanager->get_controller('rubric');
    if (!$controller) {
        return null;
    }

    $definition = $controller->get_definition();
    if (empty($definition) || empty($definition->rubric_criteria)) {
        return null;
    }

    $rubric = [
        'title' => $definition->name ?? get_string('default_rubric_name', 'local_assign_ai_rag'),
        'description' => $definition->description ?? '',
        'criteria' => [],
    ];

    foreach ($definition->rubric_criteria as $criterionid => $criterion) {
        $crit = [
            'criterion' => $criterion['description'],
            'levels' => [],
        ];

        foreach ($criterion['levels'] as $levelid => $level) {
            $crit['levels'][] = [
                'points' => (float) $level['score'],
                'description' => $level['definition'],
            ];
        }

        $rubric['criteria'][] = $crit;
    }

    return $rubric;
}

/**
 * Retrieves cached configuration for a given assignment instance.
 *
 * @param int $assignmentid The assignment instance ID (from {assign}).
 * @return stdClass|null
 */
function local_assign_ai_rag_get_assignment_config(int $assignmentid) {
    global $DB;

    static $cache = [];

    if (!$assignmentid) {
        return null;
    }

    if (!array_key_exists($assignmentid, $cache)) {
        $cache[$assignmentid] = $DB->get_record('local_assign_ai_rag_config', ['assignmentid' => $assignmentid]);
    }

    return $cache[$assignmentid];
}

/**
 * Checks whether auto-grading is enabled for a given assignment.
 *
 * @param assign $assign Assignment instance.
 * @return bool
 */
function local_assign_ai_rag_is_autograde_enabled(assign $assign): bool {
    $config = local_assign_ai_rag_get_assignment_config($assign->get_instance()->id);
    return !empty($config) && !empty($config->autograde);
}

/**
 * Checks whether RAG (course materials) is enabled for grading.
 *
 * @param assign $assign Assignment instance.
 * @return bool
 */
function local_assign_ai_rag_use_materials(assign $assign): bool {
    $config = local_assign_ai_rag_get_assignment_config($assign->get_instance()->id);
    return empty($config) || !empty($config->use_course_materials);
}

/**
 * Applies AI feedback (grade + comments) to a submission and triggers grading events.
 *
 * @param assign $assign Assignment instance.
 * @param stdClass $record Pending AI record.
 * @param int $graderid User applying the change.
 * @return void
 */
function local_assign_ai_rag_apply_ai_feedback(assign $assign, stdClass $record, int $graderid): void {
    global $DB;

    $grade = $assign->get_user_grade($record->userid, true);
    if (!$grade) {
        debugging("No grade exists for userid={$record->userid}, assignid={$assign->get_instance()->id}.", DEBUG_DEVELOPER);
        return;
    }

    $gradepushed = false;
    $instancegrade = (float) $assign->get_instance()->grade;

    if ($record->grade !== null && $record->grade !== '') {
        if ($instancegrade > 0) {
            $gradevalue = max(0, min((float)$record->grade, $instancegrade));
            $grade->grade = $gradevalue;
            $grade->grader = $graderid;
            $gradepushed = $assign->update_grade($grade);
        } else {
            debugging('The assignment uses a scale; automatic numeric grading is not supported.', DEBUG_DEVELOPER);
        }
    }

    // Build the HTML feedback. The AI message is plain text, so escape it before
    // storing it with FORMAT_HTML; citations are structured objects
    // ({text, source, page}) and must be rendered field by field.
    $feedbacktext = nl2br(s((string)($record->message ?? '')));
    if (!empty($record->citations)) {
        $citations = json_decode($record->citations, true);
        if (!empty($citations) && is_array($citations)) {
            $feedbacktext .= \local_assign_ai_rag\utils::format_citations($citations);
        }
    }

    $feedback = $DB->get_record('assignfeedback_comments', ['grade' => $grade->id]);
    if ($feedback) {
        $feedback->commenttext = $feedbacktext;
        $feedback->commentformat = FORMAT_HTML;
        $DB->update_record('assignfeedback_comments', $feedback);
    } else {
        $feedback = (object)[
            'assignment' => $assign->get_instance()->id,
            'grade' => $grade->id,
            'commenttext' => $feedbacktext,
            'commentformat' => FORMAT_HTML,
        ];
        $DB->insert_record('assignfeedback_comments', $feedback);
    }

    if (!$gradepushed) {
        $event = \mod_assign\event\submission_graded::create_from_grade($assign, $grade);
        $event->trigger();
    }
}

/**
 * Gets the count of uploaded materials for a course.
 *
 * @param int $courseid Course ID.
 * @return int Number of materials.
 */
function local_assign_ai_rag_get_materials_count(int $courseid): int {
    global $DB;
    return $DB->count_records('local_assign_ai_rag_materials', ['courseid' => $courseid]);
}

/**
 * Syncs existing submitted assignments to the pending table.
 * This ensures submissions made before the plugin was installed are visible.
 *
 * @param int $cmid Course module ID of the assignment.
 * @return int Number of records synced.
 */
function local_assign_ai_rag_sync_existing_submissions(int $cmid): int {
    global $DB;

    $cm = get_coursemodule_from_id('assign', $cmid, 0, false, MUST_EXIST);
    $context = \context_module::instance($cmid);
    $course = get_course($cm->course);
    $assign = new \assign($context, $cm, $course);
    $assignment = $assign->get_instance();

    // Get all submitted submissions for this assignment.
    $submissions = $DB->get_records_sql("
        SELECT s.*, u.id as userid
        FROM {assign_submission} s
        JOIN {user} u ON u.id = s.userid AND u.deleted = 0
        WHERE s.assignment = ?
          AND s.status = ?
          AND s.latest = 1
          AND s.userid > 0
    ", [$assignment->id, ASSIGN_SUBMISSION_STATUS_SUBMITTED]);

    $synced = 0;
    $now = time();

    foreach ($submissions as $submission) {
        // Check if pending record already exists.
        $existing = \local_assign_ai_rag\assign_submission::get_pending_record((int)$cmid, (int)$submission->userid);

        if (!$existing) {
            $record = (object) [
                'courseid' => $course->id,
                'assignmentid' => $cmid,
                'userid' => $submission->userid,
                'title' => $assignment->name,
                'message' => null,
                'grade' => null,
                'rubric_response' => null,
                'citations' => null,
                'confidence' => null,
                'retrieved_docs' => null,
                'status' => \local_assign_ai_rag\assign_submission::STATUS_INITIAL,
                'usermodified' => $submission->userid,
                'timecreated' => $now,
                'timemodified' => $now,
            ];
            $DB->insert_record('local_assign_ai_rag_pending', $record);
            $synced++;
        }
    }

    return $synced;
}
