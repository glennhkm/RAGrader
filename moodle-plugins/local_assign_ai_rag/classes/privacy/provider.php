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
namespace local_assign_ai_rag\privacy;

use core_privacy\local\metadata\collection;
use core_privacy\local\request\approved_contextlist;
use core_privacy\local\request\approved_userlist;
use core_privacy\local\request\contextlist;
use core_privacy\local\request\transform;
use core_privacy\local\request\userlist;
use core_privacy\local\request\writer;

/**
 * Privacy provider for local_assign_ai_rag.
 *
 * Pending AI results (assignmentid holds the course module id of a core
 * assign activity) belong to the student. Config, rubric and material rows only
 * carry teacher references (usermodified, graderid), which are anonymised to 0.
 *
 * @package    local_assign_ai_rag
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
        $collection->add_database_table('local_assign_ai_rag_pending', [
            'userid' => 'privacy:metadata:pending:userid',
            'message' => 'privacy:metadata:pending:message',
            'grade' => 'privacy:metadata:pending:grade',
            'rubric_response' => 'privacy:metadata:pending:rubric_response',
            'citations' => 'privacy:metadata:pending:citations',
            'confidence' => 'privacy:metadata:pending:confidence',
            'retrieved_docs' => 'privacy:metadata:pending:retrieved_docs',
            'usermodified' => 'privacy:metadata:usermodified',
        ], 'privacy:metadata:pending');

        $collection->add_database_table('local_assign_ai_rag_config', [
            'graderid' => 'privacy:metadata:config:graderid',
            'usermodified' => 'privacy:metadata:usermodified',
        ], 'privacy:metadata:config');

        $collection->add_database_table('local_assign_ai_rag_rubric', [
            'usermodified' => 'privacy:metadata:usermodified',
        ], 'privacy:metadata:rubric');

        $collection->add_database_table('local_assign_ai_rag_materials', [
            'usermodified' => 'privacy:metadata:usermodified',
        ], 'privacy:metadata:materials');

        $collection->add_external_location_link('rag_server', [
            'question' => 'privacy:metadata:rag_server:question',
            'answertext' => 'privacy:metadata:rag_server:answertext',
            'rubric' => 'privacy:metadata:rag_server:rubric',
        ], 'privacy:metadata:rag_server');

        return $collection;
    }

    /**
     * Get the contexts holding data about the user.
     *
     * @param int $userid The user id.
     * @return contextlist The contexts.
     */
    public static function get_contexts_for_userid(int $userid): contextlist {
        $contextlist = new contextlist();
        $modsql = "SELECT ctx.id
                      FROM {context} ctx
                      JOIN {course_modules} cm ON cm.id = ctx.instanceid AND ctx.contextlevel = :modlevel
                      JOIN {local_assign_ai_rag_pending} p ON p.assignmentid = cm.id
                     WHERE p.userid = :u1 OR p.usermodified = :u2
                 UNION
                    SELECT ctx.id
                      FROM {context} ctx
                      JOIN {course_modules} cm ON cm.id = ctx.instanceid AND ctx.contextlevel = :modlevel2
                      JOIN {local_assign_ai_rag_config} c ON c.assignmentid = cm.id
                     WHERE c.usermodified = :u3 OR c.graderid = :u4
                 UNION
                    SELECT ctx.id
                      FROM {context} ctx
                      JOIN {course_modules} cm ON cm.id = ctx.instanceid AND ctx.contextlevel = :modlevel3
                      JOIN {local_assign_ai_rag_rubric} r ON r.assignmentid = cm.id
                     WHERE r.usermodified = :u5
                 UNION
                    SELECT ctx.id
                      FROM {context} ctx
                      JOIN {local_assign_ai_rag_materials} m ON m.courseid = ctx.instanceid
                     WHERE ctx.contextlevel = :courselevel AND m.usermodified = :u6";
        $contextlist->add_from_sql($modsql, [
            'modlevel' => CONTEXT_MODULE, 'modlevel2' => CONTEXT_MODULE, 'modlevel3' => CONTEXT_MODULE,
            'courselevel' => CONTEXT_COURSE,
            'u1' => $userid, 'u2' => $userid, 'u3' => $userid, 'u4' => $userid, 'u5' => $userid, 'u6' => $userid,
        ]);
        return $contextlist;
    }

    /**
     * List the users with data in a context.
     *
     * @param userlist $userlist The userlist to fill.
     */
    public static function get_users_in_context(userlist $userlist): void {
        $context = $userlist->get_context();
        if ($context instanceof \context_module) {
            $params = ['cmid' => $context->instanceid];
            $userlist->add_from_sql('userid', "SELECT userid FROM {local_assign_ai_rag_pending} WHERE assignmentid = :cmid", $params);
            $userlist->add_from_sql('usermodified', "SELECT usermodified FROM {local_assign_ai_rag_pending}
                WHERE assignmentid = :cmid AND usermodified IS NOT NULL AND usermodified > 0", $params);
            $userlist->add_from_sql('usermodified', "SELECT usermodified FROM {local_assign_ai_rag_config}
                WHERE assignmentid = :cmid AND usermodified IS NOT NULL AND usermodified > 0", $params);
            $userlist->add_from_sql('graderid', "SELECT graderid FROM {local_assign_ai_rag_config}
                WHERE assignmentid = :cmid AND graderid IS NOT NULL AND graderid > 0", $params);
            $userlist->add_from_sql('usermodified', "SELECT usermodified FROM {local_assign_ai_rag_rubric}
                WHERE assignmentid = :cmid AND usermodified IS NOT NULL AND usermodified > 0", $params);
        } else if ($context instanceof \context_course) {
            $userlist->add_from_sql('usermodified', "SELECT usermodified FROM {local_assign_ai_rag_materials}
                WHERE courseid = :courseid AND usermodified IS NOT NULL AND usermodified > 0", ['courseid' => $context->instanceid]);
        }
    }

    /**
     * Export the user's pending AI results.
     *
     * @param approved_contextlist $contextlist The approved contexts.
     */
    public static function export_user_data(approved_contextlist $contextlist): void {
        global $DB;

        if (!$contextlist->count()) {
            return;
        }
        $userid = $contextlist->get_user()->id;
        foreach ($contextlist->get_contexts() as $context) {
            if (!$context instanceof \context_module) {
                continue;
            }
            $rows = $DB->get_records('local_assign_ai_rag_pending', [
                'assignmentid' => $context->instanceid,
                'userid' => $userid,
            ], 'id');
            if (!$rows) {
                continue;
            }
            $records = [];
            foreach ($rows as $row) {
                $records[] = (object)[
                    'title' => $row->title,
                    'status' => $row->status,
                    'message' => $row->message,
                    'grade' => $row->grade,
                    'rubric_response' => $row->rubric_response,
                    'citations' => $row->citations,
                    'confidence' => $row->confidence,
                    'retrieved_docs' => $row->retrieved_docs,
                    'timecreated' => transform::datetime((int)$row->timecreated),
                    'timemodified' => transform::datetime((int)$row->timemodified),
                ];
            }
            writer::with_context($context)->export_data(
                [get_string('privacy:path:pending', 'local_assign_ai_rag')],
                (object)['pending' => $records]
            );
        }
    }

    /**
     * Delete all students' pending results in a context. Config, rubric and
     * material rows hold no student data and are kept.
     *
     * @param \context $context The context.
     */
    public static function delete_data_for_all_users_in_context(\context $context): void {
        global $DB;

        if ($context instanceof \context_module) {
            $DB->delete_records('local_assign_ai_rag_pending', ['assignmentid' => $context->instanceid]);
        }
    }

    /**
     * Delete the user's pending rows and anonymise their teacher references.
     *
     * @param approved_contextlist $contextlist The approved contexts.
     */
    public static function delete_data_for_user(approved_contextlist $contextlist): void {
        $userid = $contextlist->get_user()->id;
        foreach ($contextlist->get_contexts() as $context) {
            self::erase_user($context, [$userid]);
        }
    }

    /**
     * Delete several users' data in one context.
     *
     * @param approved_userlist $userlist The approved users.
     */
    public static function delete_data_for_users(approved_userlist $userlist): void {
        if ($userlist->get_userids()) {
            self::erase_user($userlist->get_context(), $userlist->get_userids());
        }
    }

    /**
     * Delete pending rows of the users and set their teacher references to 0.
     *
     * @param \context $context The context.
     * @param int[] $userids The user ids.
     */
    private static function erase_user(\context $context, array $userids): void {
        global $DB;

        [$insql, $inparams] = $DB->get_in_or_equal($userids, SQL_PARAMS_NAMED);
        if ($context instanceof \context_module) {
            $cmid = $context->instanceid;
            $DB->delete_records_select(
                'local_assign_ai_rag_pending',
                "assignmentid = :cmid AND userid {$insql}",
                ['cmid' => $cmid] + $inparams
            );
            $DB->set_field_select(
                'local_assign_ai_rag_pending',
                'usermodified',
                0,
                "assignmentid = :cmid AND usermodified {$insql}",
                ['cmid' => $cmid] + $inparams
            );
            foreach (['local_assign_ai_rag_config' => ['usermodified', 'graderid'],
                    'local_assign_ai_rag_rubric' => ['usermodified']] as $table => $fields) {
                foreach ($fields as $field) {
                    $DB->set_field_select(
                        $table,
                        $field,
                        0,
                        "assignmentid = :cmid AND {$field} {$insql}",
                        ['cmid' => $cmid] + $inparams
                    );
                }
            }
        } else if ($context instanceof \context_course) {
            $DB->set_field_select(
                'local_assign_ai_rag_materials',
                'usermodified',
                0,
                "courseid = :courseid AND usermodified {$insql}",
                ['courseid' => $context->instanceid] + $inparams
            );
        }
    }
}
