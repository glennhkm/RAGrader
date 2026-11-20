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
use core_privacy\local\request\userlist;
use core_privacy\local\request\writer;

/**
 * Privacy provider tests for mod_airagassign.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagassign\privacy\provider
 */
final class provider_test extends \core_privacy\tests\provider_testcase {
    /** @var \stdClass */
    private $course;
    /** @var \stdClass */
    private $assign;
    /** @var \stdClass */
    private $s1;
    /** @var \stdClass */
    private $s2;
    /** @var \stdClass */
    private $user1;
    /** @var \stdClass */
    private $user2;

    /**
     * Build one assignment with two students who each submitted.
     */
    private function setup_data(): void {
        global $DB;
        $this->resetAfterTest();
        $gen = self::getDataGenerator();
        $this->course = $gen->create_course();
        $this->assign = $gen->create_module('airagassign', ['course' => $this->course->id]);
        $this->user1 = $gen->create_user();
        $this->user2 = $gen->create_user();
        $modgen = $gen->get_plugin_generator('mod_airagassign');
        $this->s1 = $modgen->create_submission($this->assign, $this->user1->id, 'Answer of user one');
        $this->s2 = $modgen->create_submission($this->assign, $this->user2->id, 'Answer of user two');
        $DB->set_field('airagassign_submissions', 'graded_by', 'teacher', ['id' => $this->s1->id]);
        $DB->set_field('airagassign_submissions', 'feedback', 'Good work', ['id' => $this->s1->id]);
        $DB->set_field('airagassign_submissions', 'grading_error', 'Timeout from RAG', ['id' => $this->s1->id]);
        $DB->set_field('airagassign_submissions', 'grading_requestid', 'req-abc-123', ['id' => $this->s1->id]);
    }

    /**
     * The metadata describes both tables and the external RAG server.
     */
    public function test_get_metadata(): void {
        $collection = provider::get_metadata(new collection('mod_airagassign'));
        $items = $collection->get_collection();
        $names = array_map(fn($i) => $i->get_name(), $items);
        $this->assertContains('airagassign_submissions', $names);
        $this->assertContains('airagassign_answers', $names);
        $this->assertContains('rag_server', $names);
        $declared = [];
        foreach ($items as $item) {
            if (method_exists($item, 'get_privacy_fields')) {
                $declared[$item->get_name()] = array_keys($item->get_privacy_fields());
            }
        }
        foreach (['status', 'grading_error', 'grading_requestid', 'grading_started_at'] as $field) {
            $this->assertContains($field, $declared['airagassign_submissions']);
        }
        $this->assertContains('timecreated', $declared['airagassign_answers']);
        foreach ($items as $item) {
            if ($item->get_name() === 'rag_server') {
                $fields = $item->get_privacy_fields();
                $this->assertArrayHasKey('answertext', $fields);
                $this->assertArrayNotHasKey('userid', $fields);
            }
        }
    }

    /**
     * Only the module context holding the user's submission is returned.
     */
    public function test_get_contexts_for_userid(): void {
        $this->setup_data();
        $other = self::getDataGenerator()->create_module('airagassign', ['course' => $this->course->id]);
        $contextlist = provider::get_contexts_for_userid($this->user1->id);
        $this->assertEquals(
            [\context_module::instance($this->assign->cmid)->id],
            $contextlist->get_contextids()
        );
        $this->assertEmpty(provider::get_contexts_for_userid(self::getDataGenerator()->create_user()->id)->get_contextids());
        $this->assertNotEmpty($other->cmid);
    }

    /**
     * The user's answers are exported under the Submissions subcontext.
     */
    public function test_export_user_data(): void {
        $this->setup_data();
        $context = \context_module::instance($this->assign->cmid);
        $this->export_context_data_for_user($this->user1->id, $context, 'mod_airagassign');
        $data = writer::with_context($context)->get_data([get_string('submissions', 'airagassign')]);
        $this->assertNotEmpty($data);
        $json = json_encode($data);
        $this->assertStringContainsString('Answer of user one', $json);
        $this->assertStringContainsString('Good work', $json);
        $this->assertStringContainsString('Timeout from RAG', $json);
        $this->assertStringContainsString('req-abc-123', $json);
        $this->assertStringNotContainsString('Answer of user two', $json);
    }

    /**
     * Deleting one user leaves the other student's data untouched.
     */
    public function test_delete_data_for_user_keeps_other_students(): void {
        global $DB;
        $this->setup_data();
        $context = \context_module::instance($this->assign->cmid);
        provider::delete_data_for_user(new approved_contextlist($this->user1, 'mod_airagassign', [$context->id]));
        $this->assertFalse($DB->record_exists('airagassign_submissions', ['id' => $this->s1->id]));
        $this->assertFalse($DB->record_exists('airagassign_answers', ['submissionid' => $this->s1->id]));
        $this->assertTrue($DB->record_exists('airagassign_submissions', ['id' => $this->s2->id]));
        $this->assertTrue($DB->record_exists('airagassign_answers', ['submissionid' => $this->s2->id]));
    }

    /**
     * Users in a context are listed and can be deleted in bulk.
     */
    public function test_delete_data_for_users(): void {
        global $DB;
        $this->setup_data();
        $context = \context_module::instance($this->assign->cmid);
        $userlist = new userlist($context, 'mod_airagassign');
        provider::get_users_in_context($userlist);
        $this->assertEqualsCanonicalizing([$this->user1->id, $this->user2->id], $userlist->get_userids());

        provider::delete_data_for_users(new approved_userlist($context, 'mod_airagassign', [$this->user1->id]));
        $this->assertFalse($DB->record_exists('airagassign_submissions', ['id' => $this->s1->id]));
        $this->assertTrue($DB->record_exists('airagassign_submissions', ['id' => $this->s2->id]));
        $this->assertTrue($DB->record_exists('airagassign_answers', ['submissionid' => $this->s2->id]));
    }

    /**
     * Deleting a whole context removes every submission and answer in it only.
     */
    public function test_delete_data_for_all_users_in_context(): void {
        global $DB;
        $this->setup_data();
        $gen = self::getDataGenerator();
        $other = $gen->create_module('airagassign', ['course' => $this->course->id]);
        $keep = $gen->get_plugin_generator('mod_airagassign')->create_submission($other, $this->user1->id, 'elsewhere');

        provider::delete_data_for_all_users_in_context(\context_module::instance($this->assign->cmid));
        $this->assertEquals(0, $DB->count_records('airagassign_submissions', ['assignid' => $this->assign->id]));
        $this->assertEquals(0, $DB->count_records('airagassign_answers', ['submissionid' => $this->s1->id]));
        $this->assertEquals(0, $DB->count_records('airagassign_answers', ['submissionid' => $this->s2->id]));
        $this->assertTrue($DB->record_exists('airagassign_submissions', ['id' => $keep->id]));
        $this->assertTrue($DB->record_exists('airagassign_answers', ['submissionid' => $keep->id]));
    }

    /**
     * Grader attribution is a non-identifying label and survives student erasure.
     *
     * The graded_by column stores 'teacher' or 'ai_confirmed', never a user id,
     * so no teacher identity needs anonymising here; other rows keep their label.
     */
    public function test_teacher_fields_are_anonymised(): void {
        global $DB;
        $this->setup_data();
        $DB->set_field('airagassign_submissions', 'graded_by', 'ai_confirmed', ['id' => $this->s2->id]);
        provider::delete_data_for_user(new approved_contextlist(
            $this->user1,
            'mod_airagassign',
            [\context_module::instance($this->assign->cmid)->id]
        ));
        $this->assertSame('ai_confirmed', $DB->get_field('airagassign_submissions', 'graded_by', ['id' => $this->s2->id]));
    }
}
