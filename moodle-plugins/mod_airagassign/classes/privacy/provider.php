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
namespace mod_airagassign\privacy;

use core_privacy\local\metadata\collection;
use core_privacy\local\request\approved_contextlist;
use core_privacy\local\request\approved_userlist;
use core_privacy\local\request\contextlist;
use core_privacy\local\request\helper;
use core_privacy\local\request\transform;
use core_privacy\local\request\userlist;
use core_privacy\local\request\writer;

/**
 * Privacy provider for mod_airagassign.
 *
 * Personal data lives in the submissions and answers tables. The graded_by
 * column holds a non-identifying label ('teacher' or 'ai_confirmed'), not a
 * user id, so no teacher identity is stored by this plugin.
 *
 * @package    mod_airagassign
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class provider implements
    \core_privacy\local\metadata\provider,
    \core_privacy\local\request\plugin\provider,
    \core_privacy\local\request\core_userlist_provider {
    /**
     * Describe the stored and exported data.
     *
     * @param collection $collection The collection to extend.
     * @return collection The extended collection.
     */
    public static function get_metadata(collection $collection): collection {
        $collection->add_database_table('airagassign_submissions', [
            'userid' => 'privacy:metadata:airagassign_submissions:userid',
            'grade' => 'privacy:metadata:airagassign_submissions:grade',
            'ai_grade' => 'privacy:metadata:airagassign_submissions:ai_grade',
            'ai_feedback' => 'privacy:metadata:airagassign_submissions:ai_feedback',
            'feedback' => 'privacy:metadata:airagassign_submissions:feedback',
            'ai_response' => 'privacy:metadata:airagassign_submissions:ai_response',
            'graded_by' => 'privacy:metadata:airagassign_submissions:graded_by',
            'teacher_note' => 'privacy:metadata:airagassign_submissions:teacher_note',
            'confidence' => 'privacy:metadata:airagassign_submissions:confidence',
            'timecreated' => 'privacy:metadata:airagassign_submissions:timecreated',
            'timegraded' => 'privacy:metadata:airagassign_submissions:timegraded',
        ], 'privacy:metadata:airagassign_submissions');

        $collection->add_database_table('airagassign_answers', [
            'answertext' => 'privacy:metadata:airagassign_answers:answertext',
            'score' => 'privacy:metadata:airagassign_answers:score',
            'ai_score' => 'privacy:metadata:airagassign_answers:ai_score',
            'ai_feedback' => 'privacy:metadata:airagassign_answers:ai_feedback',
            'feedback' => 'privacy:metadata:airagassign_answers:feedback',
            'ai_response' => 'privacy:metadata:airagassign_answers:ai_response',
        ], 'privacy:metadata:airagassign_answers');

        $collection->add_external_location_link('rag_server', [
            'question' => 'privacy:metadata:rag_server:question',
            'answertext' => 'privacy:metadata:rag_server:answertext',
            'rubric' => 'privacy:metadata:rag_server:rubric',
        ], 'privacy:metadata:rag_server');

        return $collection;
    }

    /**
     * Get the module contexts where the user has a submission.
     *
     * @param int $userid The user id.
     * @return contextlist The contexts.
     */
    public static function get_contexts_for_userid(int $userid): contextlist {
        $contextlist = new contextlist();
        $sql = "SELECT ctx.id
                  FROM {context} ctx
                  JOIN {course_modules} cm ON cm.id = ctx.instanceid AND ctx.contextlevel = :contextlevel
                  JOIN {modules} m ON m.id = cm.module AND m.name = :modname
                  JOIN {airagassign_submissions} s ON s.assignid = cm.instance
                 WHERE s.userid = :userid";
        $contextlist->add_from_sql($sql, [
            'contextlevel' => CONTEXT_MODULE,
            'modname' => 'airagassign',
            'userid' => $userid,
        ]);
        return $contextlist;
    }

    /**
     * List the users who have data in a context.
     *
     * @param userlist $userlist The userlist to fill.
     */
    public static function get_users_in_context(userlist $userlist): void {
        $context = $userlist->get_context();
        if (!$context instanceof \context_module) {
            return;
        }
        $sql = "SELECT s.userid
                  FROM {course_modules} cm
                  JOIN {modules} m ON m.id = cm.module AND m.name = :modname
                  JOIN {airagassign_submissions} s ON s.assignid = cm.instance
                 WHERE cm.id = :cmid";
        $userlist->add_from_sql('userid', $sql, ['modname' => 'airagassign', 'cmid' => $context->instanceid]);
    }

    /**
     * Export the user's submissions and answers.
     *
     * @param approved_contextlist $contextlist The approved contexts.
     */
    public static function export_user_data(approved_contextlist $contextlist): void {
        global $DB;

        if (!$contextlist->count()) {
            return;
        }
        $user = $contextlist->get_user();
        [$insql, $inparams] = $DB->get_in_or_equal($contextlist->get_contextids(), SQL_PARAMS_NAMED);
        $sql = "SELECT ctx.id AS contextid, cm.id AS cmid, s.*
                  FROM {context} ctx
                  JOIN {course_modules} cm ON cm.id = ctx.instanceid AND ctx.contextlevel = :contextlevel
                  JOIN {modules} m ON m.id = cm.module AND m.name = :modname
                  JOIN {airagassign_submissions} s ON s.assignid = cm.instance
                 WHERE s.userid = :userid AND ctx.id {$insql}
              ORDER BY s.id";
        $params = ['contextlevel' => CONTEXT_MODULE, 'modname' => 'airagassign', 'userid' => $user->id] + $inparams;
        $submissions = $DB->get_recordset_sql($sql, $params);

        $bycontext = [];
        foreach ($submissions as $s) {
            $answers = [];
            foreach ($DB->get_records('airagassign_answers', ['submissionid' => $s->id], 'id') as $a) {
                $answers[] = [
                    'answertext' => $a->answertext,
                    'score' => $a->score,
                    'ai_score' => $a->ai_score,
                    'ai_feedback' => $a->ai_feedback,
                    'feedback' => $a->feedback,
                    'ai_response' => $a->ai_response,
                ];
            }
            $bycontext[$s->contextid][] = (object)[
                'status' => $s->status,
                'grade' => $s->grade,
                'ai_grade' => $s->ai_grade,
                'ai_feedback' => $s->ai_feedback,
                'feedback' => $s->feedback,
                'ai_response' => $s->ai_response,
                'graded_by' => $s->graded_by,
                'teacher_note' => $s->teacher_note,
                'confidence' => $s->confidence,
                'timecreated' => transform::datetime($s->timecreated),
                'timegraded' => $s->timegraded ? transform::datetime($s->timegraded) : null,
                'answers' => $answers,
            ];
        }
        $submissions->close();

        foreach ($bycontext as $contextid => $records) {
            $context = \context::instance_by_id($contextid);
            writer::with_context($context)->export_data(
                [get_string('submissions', 'airagassign')],
                (object)['submissions' => $records]
            );
            helper::export_context_files($context, $user);
        }
    }

    /**
     * Delete all submissions and answers in a context.
     *
     * @param \context $context The context.
     */
    public static function delete_data_for_all_users_in_context(\context $context): void {
        if (!$context instanceof \context_module) {
            return;
        }
        $cm = get_coursemodule_from_id('airagassign', $context->instanceid);
        if (!$cm) {
            return;
        }
        self::delete_submissions(['assignid' => $cm->instance]);
    }

    /**
     * Delete one user's submissions and answers in the approved contexts.
     *
     * @param approved_contextlist $contextlist The approved contexts.
     */
    public static function delete_data_for_user(approved_contextlist $contextlist): void {
        $userid = $contextlist->get_user()->id;
        foreach ($contextlist->get_contexts() as $context) {
            if (!$context instanceof \context_module) {
                continue;
            }
            $cm = get_coursemodule_from_id('airagassign', $context->instanceid);
            if ($cm) {
                self::delete_submissions(['assignid' => $cm->instance, 'userid' => $userid]);
            }
        }
    }

    /**
     * Delete several users' submissions and answers in one context.
     *
     * @param approved_userlist $userlist The approved users.
     */
    public static function delete_data_for_users(approved_userlist $userlist): void {
        global $DB;

        $context = $userlist->get_context();
        $userids = $userlist->get_userids();
        if (!$context instanceof \context_module || !$userids) {
            return;
        }
        $cm = get_coursemodule_from_id('airagassign', $context->instanceid);
        if (!$cm) {
            return;
        }
        [$insql, $inparams] = $DB->get_in_or_equal($userids, SQL_PARAMS_NAMED);
        $ids = $DB->get_fieldset_select(
            'airagassign_submissions',
            'id',
            "assignid = :assignid AND userid {$insql}",
            ['assignid' => $cm->instance] + $inparams
        );
        self::delete_submission_ids($ids);
    }

    /**
     * Delete submissions (and their answers) matching a set of conditions.
     *
     * @param array $conditions Column => value conditions.
     */
    private static function delete_submissions(array $conditions): void {
        global $DB;
        self::delete_submission_ids($DB->get_fieldset('airagassign_submissions', 'id', $conditions));
    }

    /**
     * Delete submissions and their answers by id.
     *
     * @param int[] $ids Submission ids.
     */
    private static function delete_submission_ids(array $ids): void {
        global $DB;
        if (!$ids) {
            return;
        }
        foreach (array_chunk($ids, 500) as $chunk) {
            [$insql, $inparams] = $DB->get_in_or_equal($chunk);
            $DB->delete_records_select('airagassign_answers', "submissionid {$insql}", $inparams);
            $DB->delete_records_select('airagassign_submissions', "id {$insql}", $inparams);
        }
    }
}
