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
use core_privacy\local\request\userlist;
use core_privacy\local\request\writer;

/**
 * Privacy provider tests for local_assign_ai_rag.
 *
 * @package    local_assign_ai_rag
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \local_assign_ai_rag\privacy\provider
 */
final class provider_test extends \core_privacy\tests\provider_testcase {
    /** @var \stdClass */
    private $course;
    /** @var \stdClass */
    private $assign;
    /** @var \stdClass */
    private $student1;
    /** @var \stdClass */
    private $student2;
    /** @var \stdClass */
    private $teacher;

    /**
     * Build an assign cm with two pending rows, config, rubric and a course material.
     */
    private function setup_data(): void {
        global $DB;
        $this->resetAfterTest();
        $gen = self::getDataGenerator();
        $this->course = $gen->create_course();
        $this->assign = $gen->create_module('assign', ['course' => $this->course->id]);
        $this->student1 = $gen->create_user();
        $this->student2 = $gen->create_user();
        $this->teacher = $gen->create_user();
        $now = time();
        foreach ([$this->student1, $this->student2] as $i => $student) {
            $DB->insert_record('local_assign_ai_rag_pending', (object)[
                'courseid' => $this->course->id,
                'assignmentid' => $this->assign->cmid,
                'title' => 'Essay',
                'userid' => $student->id,
                'message' => 'Pending feedback ' . ($i + 1),
                'grade' => 70,
                'status' => 'pending',
                'usermodified' => $this->teacher->id,
                'timecreated' => $now,
                'timemodified' => $now,
            ]);
        }
        $DB->insert_record('local_assign_ai_rag_config', (object)[
            'assignmentid' => $this->assign->cmid,
            'autograde' => 1,
            'graderid' => $this->teacher->id,
            'usermodified' => $this->teacher->id,
            'timecreated' => $now,
            'timemodified' => $now,
        ]);
        $DB->insert_record('local_assign_ai_rag_rubric', (object)[
            'assignmentid' => $this->assign->cmid,
            'rubric_json' => '{}',
            'usermodified' => $this->teacher->id,
            'timecreated' => $now,
            'timemodified' => $now,
        ]);
        $DB->insert_record('local_assign_ai_rag_materials', (object)[
            'courseid' => $this->course->id,
            'filename' => 'a.pdf',
            'contenthash' => str_repeat('a', 40),
            'filetype' => 'pdf',
            'usermodified' => $this->teacher->id,
            'timecreated' => $now,
        ]);
    }

    /**
     * Metadata covers the tables and the external RAG server.
     */
    public function test_get_metadata(): void {
        $items = provider::get_metadata(new collection('local_assign_ai_rag'))->get_collection();
        $names = array_map(fn($i) => $i->get_name(), $items);
        foreach (['local_assign_ai_rag_pending', 'local_assign_ai_rag_config', 'local_assign_ai_rag_rubric',
                'local_assign_ai_rag_materials', 'rag_server'] as $expected) {
            $this->assertContains($expected, $names);
        }
    }

    /**
     * Students get the module context; the teacher gets module and course contexts.
     */
    public function test_get_contexts_for_userid(): void {
        $this->setup_data();
        $modctx = \context_module::instance($this->assign->cmid)->id;
        $coursectx = \context_course::instance($this->course->id)->id;
        $this->assertEquals([$modctx], provider::get_contexts_for_userid($this->student1->id)->get_contextids());
        $this->assertEqualsCanonicalizing(
            [$modctx, $coursectx],
            provider::get_contexts_for_userid($this->teacher->id)->get_contextids()
        );
    }

    /**
     * The student's pending result is exported to the module context.
     */
    public function test_export_user_data(): void {
        $this->setup_data();
        $context = \context_module::instance($this->assign->cmid);
        $this->export_context_data_for_user($this->student1->id, $context, 'local_assign_ai_rag');
        $data = writer::with_context($context)->get_data([get_string('privacy:path:pending', 'local_assign_ai_rag')]);
        $json = json_encode($data);
        $this->assertStringContainsString('Pending feedback 1', $json);
        $this->assertStringNotContainsString('Pending feedback 2', $json);
    }

    /**
     * Deleting a student removes only their pending rows.
     */
    public function test_delete_data_for_user_keeps_other_students(): void {
        global $DB;
        $this->setup_data();
        $context = \context_module::instance($this->assign->cmid);
        provider::delete_data_for_user(new approved_contextlist($this->student1, 'local_assign_ai_rag', [$context->id]));
        $this->assertFalse($DB->record_exists('local_assign_ai_rag_pending', ['userid' => $this->student1->id]));
        $this->assertTrue($DB->record_exists('local_assign_ai_rag_pending', ['userid' => $this->student2->id]));
    }

    /**
     * Bulk deletion by userlist.
     */
    public function test_delete_data_for_users(): void {
        global $DB;
        $this->setup_data();
        $context = \context_module::instance($this->assign->cmid);
        $userlist = new userlist($context, 'local_assign_ai_rag');
        provider::get_users_in_context($userlist);
        $this->assertEqualsCanonicalizing(
            [$this->student1->id, $this->student2->id, $this->teacher->id],
            $userlist->get_userids()
        );
        provider::delete_data_for_users(new approved_userlist($context, 'local_assign_ai_rag', [$this->student2->id]));
        $this->assertFalse($DB->record_exists('local_assign_ai_rag_pending', ['userid' => $this->student2->id]));
        $this->assertTrue($DB->record_exists('local_assign_ai_rag_pending', ['userid' => $this->student1->id]));
    }

    /**
     * Context deletion drops pending rows in that context only.
     */
    public function test_delete_data_for_all_users_in_context(): void {
        global $DB;
        $this->setup_data();
        $other = self::getDataGenerator()->create_module('assign', ['course' => $this->course->id]);
        $DB->insert_record('local_assign_ai_rag_pending', (object)[
            'courseid' => $this->course->id, 'assignmentid' => $other->cmid, 'title' => 'x',
            'userid' => $this->student1->id, 'status' => 'pending',
        ]);
        provider::delete_data_for_all_users_in_context(\context_module::instance($this->assign->cmid));
        $this->assertEquals(0, $DB->count_records('local_assign_ai_rag_pending', ['assignmentid' => $this->assign->cmid]));
        $this->assertEquals(1, $DB->count_records('local_assign_ai_rag_config', ['assignmentid' => $this->assign->cmid]));
        $this->assertEquals(1, $DB->count_records('local_assign_ai_rag_rubric', ['assignmentid' => $this->assign->cmid]));
        $this->assertEquals(1, $DB->count_records('local_assign_ai_rag_pending', ['assignmentid' => $other->cmid]));
        $this->assertEquals(1, $DB->count_records('local_assign_ai_rag_materials'));
    }

    /**
     * Teacher references are set to 0 while the rows are kept.
     */
    public function test_teacher_fields_are_anonymised(): void {
        global $DB;
        $this->setup_data();
        $modctx = \context_module::instance($this->assign->cmid)->id;
        $coursectx = \context_course::instance($this->course->id)->id;
        provider::delete_data_for_user(new approved_contextlist(
            $this->teacher,
            'local_assign_ai_rag',
            [$modctx, $coursectx]
        ));
        $this->assertEquals(2, $DB->count_records('local_assign_ai_rag_pending', ['usermodified' => 0]));
        $this->assertEquals(0, $DB->get_field('local_assign_ai_rag_config', 'usermodified', ['assignmentid' => $this->assign->cmid]));
        $this->assertEquals(0, $DB->get_field('local_assign_ai_rag_config', 'graderid', ['assignmentid' => $this->assign->cmid]));
        $this->assertEquals(0, $DB->get_field('local_assign_ai_rag_rubric', 'usermodified', ['assignmentid' => $this->assign->cmid]));
        $this->assertEquals(0, $DB->get_field('local_assign_ai_rag_materials', 'usermodified', ['courseid' => $this->course->id]));
        $this->assertEquals(2, $DB->count_records('local_assign_ai_rag_pending'));
    }
}
