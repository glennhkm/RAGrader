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

namespace mod_airagassign\local;

/**
 * Characterization tests for the rubric payload builder.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagassign\local\rubric_builder
 */
final class rubric_builder_test extends \advanced_testcase {
    /**
     * Load lib.php (needed by the old functions and by add_instance callers).
     */
    public static function setUpBeforeClass(): void {
        global $CFG;
        parent::setUpBeforeClass();
        require_once($CFG->dirroot . '/mod/airagassign/lib.php');
    }

    /**
     * Custom criteria become a name => {description, max_score} map in sort order.
     */
    public function test_build_custom_criteria(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id,
            'rubricmode' => 'custom',
            'criterionname' => ['Accuracy', 'Clarity'],
            'criteriondesc' => ['Facts are correct', 'Easy to follow'],
            'criterionmaxscore' => [50, 20],
        ]);

        $this->assertSame([
            'Accuracy' => ['description' => 'Facts are correct', 'max_score' => 50.0],
            'Clarity' => ['description' => 'Easy to follow', 'max_score' => 20.0],
        ], rubric_builder::build($assign->id));
    }

    /**
     * Simple mode and unknown assignments send no rubric.
     */
    public function test_build_simple_and_missing(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id,
            'rubricmode' => 'simple',
        ]);

        $this->assertSame([], rubric_builder::build($assign->id));
        $this->assertSame([], rubric_builder::build(-1));
    }

    /**
     * A Moodle-rubric assignment whose rubric has not been defined yet yields [].
     */
    public function test_build_moodle_rubric_without_definition(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id,
            'rubricmode' => 'moodle',
        ]);

        $this->assertSame([], rubric_builder::build($assign->id));
        $this->assertSame([], rubric_builder::build_moodle($assign));
    }

    /**
     * A defined Moodle rubric becomes criterion => level list with the top score as max.
     */
    public function test_build_moodle_rubric_with_definition(): void {
        $this->resetAfterTest();
        $this->setAdminUser();
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id,
            'rubricmode' => 'moodle',
        ]);
        $context = \context_module::instance($assign->cmid);
        $this->getDataGenerator()->get_plugin_generator('gradingform_rubric')->create_instance(
            $context, 'mod_airagassign', 'submissions', 'Essay rubric', '', [
                'Argument' => ['Weak' => 0, 'Strong' => 10],
                'Style' => ['Poor' => 1, 'Fine' => 4],
            ]);

        $this->assertSame([
            'Argument' => ['description' => "- Weak (0 pts)\n- Strong (10 pts)", 'max_score' => 10.0],
            'Style' => ['description' => "- Poor (1 pts)\n- Fine (4 pts)", 'max_score' => 4.0],
        ], rubric_builder::build($assign->id));
    }

    /**
     * Syncing enables Moodle rubric for 'moodle' mode and disables it otherwise.
     *
     * During add_instance the course module is not linked to the instance yet, so the
     * sync is a no-op on creation; it takes effect from the first update onwards.
     */
    public function test_sync_moodle(): void {
        global $CFG;
        require_once($CFG->dirroot . '/grade/grading/lib.php');
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id,
            'rubricmode' => 'moodle',
        ]);
        $context = \context_module::instance($assign->cmid);
        $this->assertNull(get_grading_manager($context, 'mod_airagassign', 'submissions')->get_active_method());

        rubric_builder::sync_moodle((object)['id' => $assign->id, 'rubricmode' => 'moodle']);
        $this->assertSame('rubric', get_grading_manager($context, 'mod_airagassign', 'submissions')->get_active_method());

        rubric_builder::sync_moodle((object)['id' => $assign->id, 'rubricmode' => 'custom']);
        $this->assertNull(get_grading_manager($context, 'mod_airagassign', 'submissions')->get_active_method());

        // Unknown instances are ignored.
        rubric_builder::sync_moodle((object)['id' => -1, 'rubricmode' => 'moodle']);
    }
}
