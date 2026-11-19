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

namespace local_assign_ai_rag;

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/local/assign_ai_rag/locallib.php');
require_once($CFG->dirroot . '/mod/assign/locallib.php');

/**
 * Event observers for local_assign_ai_rag.
 *
 * @package     local_assign_ai_rag
 * @category    event
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class observer {
    /**
     * Handles the submission created event.
     *
     * Creates a pending record immediately so it appears in the Review page,
     * then queues an ad-hoc task for AI processing if autograde is enabled.
     *
     * @param \mod_assign\event\submission_created $event The submission created event.
     * @return void
     */
    public static function submission_created(\mod_assign\event\submission_created $event) {
        global $DB;

        try {
            $data = $event->get_data();
            $other = $data['other'];

            // Only process submitted assignments (not drafts).
            if ($other['submissionstatus'] !== ASSIGN_SUBMISSION_STATUS_SUBMITTED) {
                return;
            }

            $assign = $event->get_assign();
            if (!$assign) {
                return;
            }

            $userid = $data['relateduserid'] ?? null;
            if (!$userid) {
                return;
            }

            $cmid = $assign->get_course_module()->id;
            $assignment = $assign->get_instance();
            $course = $assign->get_course();

            // Check if pending record already exists.
            $existing = assign_submission::get_pending_record((int)$cmid, (int)$userid);

            if (!$existing) {
                // Create pending record immediately so it shows in Review page.
                $now = time();
                $record = (object) [
                    'courseid' => $course->id,
                    'assignmentid' => $cmid,
                    'userid' => $userid,
                    'title' => $assignment->name,
                    'message' => null,
                    'grade' => null,
                    'rubric_response' => null,
                    'citations' => null,
                    'confidence' => null,
                    'retrieved_docs' => null,
                    'status' => assign_submission::STATUS_INITIAL,
                    'usermodified' => $userid,
                    'timecreated' => $now,
                    'timemodified' => $now,
                ];
                $DB->insert_record('local_assign_ai_rag_pending', $record);
            }

            // Queue ad-hoc task for AI processing if autograde is enabled.
            if (local_assign_ai_rag_is_autograde_enabled($assign)) {
                $task = new \local_assign_ai_rag\task\process_submission_ai();
                $task->set_custom_data((object) [
                    'userid' => (int)$userid,
                    'cmid' => (int)$cmid,
                ]);
                \core\task\manager::queue_adhoc_task($task);
            }
        } catch (\Exception $e) {
            debugging('Exception in submission_created observer: ' . $e->getMessage(), DEBUG_DEVELOPER);
        }
    }

    /**
     * Normalizes a score to be saved as an int if it has no decimal places, or as a float otherwise.
     *
     * @param mixed $score Score value (string, int or float).
     * @return int|float
     */
    private static function normalize_points($score) {
        $float = (float) $score;
        return (fmod($float, 1.0) == 0.0) ? (int) $float : $float;
    }

    /**
     * Handles the grading event for a submission.
     *
     * Updates the local_assign_ai_rag_pending table with the manual grade.
     *
     * @param \mod_assign\event\submission_graded $event The grading event.
     * @return void
     */
    public static function submission_graded(\mod_assign\event\submission_graded $event) {
        global $DB;

        try {
            $data = $event->get_data();
            $cmid = $data['contextinstanceid'] ?? null;
            $userid = $data['relateduserid'] ?? null;
            $gradeid = $data['objectid'] ?? null;

            $record = assign_submission::get_pending_record((int)$cmid, (int)$userid);

            if (!$record) {
                return;
            }

            $feedback = $DB->get_record('assignfeedback_comments', ['grade' => $gradeid]);
            if ($feedback && !empty($feedback->commenttext)) {
                // The record message is plain text (it is escaped on display), so
                // convert the HTML feedback comment instead of storing raw markup.
                $record->message = content_to_text($feedback->commenttext, $feedback->commentformat);
            }

            $grade = $DB->get_record('assign_grades', ['id' => $gradeid]);
            if ($grade && isset($grade->grade)) {
                $record->grade = self::normalize_points($grade->grade);
            }

            $instances = $DB->get_records('grading_instances', [
                'itemid' => $gradeid,
                'status' => 1,
            ]);

            if ($instances) {
                foreach ($instances as $gi) {
                    $fillings = $DB->get_records('gradingform_rubric_fillings', ['instanceid' => $gi->id]);
                    if ($fillings) {
                        $rubricdata = [];
                        foreach ($fillings as $f) {
                            $criterion = $DB->get_field('gradingform_rubric_criteria', 'description', ['id' => $f->criterionid]);
                            $score = $f->levelid
                                ? $DB->get_field('gradingform_rubric_levels', 'score', ['id' => $f->levelid])
                                : 0;

                            $rubricdata[] = [
                                'criterion' => $criterion,
                                'levels' => [
                                    [
                                        'points' => self::normalize_points($score),
                                        'comment' => $f->remark ?? '',
                                    ],
                                ],
                            ];
                        }

                        $record->rubric_response = json_encode($rubricdata, JSON_UNESCAPED_UNICODE);

                        break;
                    }
                }
            }

            $record->status = assign_submission::STATUS_APPROVED;
            if (!empty($data['userid'])) {
                $record->usermodified = $data['userid'];
            }
            $record->timemodified = time();
            $DB->update_record('local_assign_ai_rag_pending', $record);
        } catch (\Exception $e) {
            debugging('Exception in submission_graded observer: ' . $e->getMessage(), DEBUG_DEVELOPER);
        }
    }

    /**
     * Resets AI pending records when a student edits a submission and multiple attempts are allowed.
     *
     * @param \mod_assign\event\submission_updated $event The submission updated event.
     * @return void
     */
    public static function submission_updated(\mod_assign\event\submission_updated $event) {
        global $DB;

        try {
            $assign = $event->get_assign();
            if (!$assign) {
                return;
            }

            $instance = $assign->get_instance();
            $maxattempts = isset($instance->maxattempts) ? (int)$instance->maxattempts : 1;
            $allowsmultiple = $maxattempts > 1 || $maxattempts === ASSIGN_UNLIMITED_ATTEMPTS;
            if (!$allowsmultiple) {
                return;
            }

            $data = $event->get_data();
            $userid = $data['relateduserid'] ?? null;
            if (!$userid) {
                return;
            }

            $cmid = $assign->get_course_module()->id;
            $record = assign_submission::get_pending_record((int)$cmid, (int)$userid);

            // 'approve' is the legacy value written by plugin versions before 1.1.2.
            if (!$record || !in_array($record->status, [assign_submission::STATUS_APPROVED, 'approve'], true)) {
                return;
            }

            $DB->delete_records('local_assign_ai_rag_pending', ['id' => $record->id]);
        } catch (\Exception $e) {
            debugging('Exception in submission_updated observer: ' . $e->getMessage(), DEBUG_DEVELOPER);
        }
    }
}
