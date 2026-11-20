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

/**
 * Data generator for mod_airagassign.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Data generator class for mod_airagassign.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class mod_airagassign_generator extends testing_module_generator {
    /**
     * Create an assignment instance. No manual file and no linked materials are
     * set by default, so no vectorization request is made.
     *
     * @param stdClass|array|null $record Instance fields to override.
     * @param array|null $options Course module options.
     * @return stdClass The created instance record (with cmid).
     */
    public function create_instance($record = null, ?array $options = null) {
        $record = (object)(array)$record;
        $defaults = [
            'assignmode' => 'essay',
            'rubricmode' => 'custom',
            'maximumgrade' => 100,
            'essayprompt' => 'Write an essay about the course materials.',
            'opendate' => 0,
            'duedate' => 0,
            'allowlate' => 0,
            'minwords' => 0,
            'maxwords' => 0,
        ];
        foreach ($defaults as $key => $value) {
            if (!isset($record->$key)) {
                $record->$key = $value;
            }
        }

        return parent::create_instance($record, (array)$options);
    }

    /**
     * Create a submission with a single (essay) answer.
     *
     * @param stdClass $assign Instance record as returned by create_instance().
     * @param int $userid Submitting user.
     * @param string $answer Answer text.
     * @param string $status Submission status.
     * @return stdClass The submission record.
     */
    public function create_submission(stdClass $assign, int $userid, string $answer, string $status = 'submitted'): stdClass {
        global $DB;

        $now = time();
        $submission = (object)[
            'assignid' => $assign->id,
            'userid' => $userid,
            'status' => $status,
            'grading_started_at' => 0,
            'timecreated' => $now,
            'timegraded' => 0,
        ];
        $submission->id = $DB->insert_record('airagassign_submissions', $submission);

        $DB->insert_record('airagassign_answers', (object)[
            'submissionid' => $submission->id,
            'questionid' => null,
            'answertext' => $answer,
            'timecreated' => $now,
        ]);

        return $submission;
    }
}
