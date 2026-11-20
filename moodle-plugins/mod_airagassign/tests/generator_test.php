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

namespace mod_airagassign;

/**
 * Smoke test for the mod_airagassign data generator.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagassign_generator
 */
final class generator_test extends \advanced_testcase {
    /**
     * An essay instance is created with the documented defaults.
     */
    public function test_create_instance(): void {
        global $DB;
        $this->resetAfterTest();

        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', ['course' => $course->id]);

        $record = $DB->get_record('airagassign', ['id' => $assign->id], '*', MUST_EXIST);
        $this->assertSame('essay', $record->assignmode);
        $this->assertSame('custom', $record->rubricmode);
        $this->assertEquals(100, $record->maximumgrade);
    }

    /**
     * A submission writes one submission row and one answer row.
     */
    public function test_create_submission(): void {
        global $DB;
        $this->resetAfterTest();

        $course = $this->getDataGenerator()->create_course();
        $student = $this->getDataGenerator()->create_user();
        $assign = $this->getDataGenerator()->create_module('airagassign', ['course' => $course->id]);
        $generator = $this->getDataGenerator()->get_plugin_generator('mod_airagassign');

        $submission = $generator->create_submission($assign, $student->id, 'My essay answer');

        $this->assertSame('submitted', $submission->status);
        $this->assertEquals(1, $DB->count_records('airagassign_submissions', ['assignid' => $assign->id]));
        $answers = $DB->get_records('airagassign_answers', ['submissionid' => $submission->id]);
        $this->assertCount(1, $answers);
        $this->assertSame('My essay answer', reset($answers)->answertext);
    }
}
