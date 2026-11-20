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
 * Tests for the instance callbacks in lib.php.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     ::airagassign_update_instance
 * @covers     ::airagassign_add_instance
 */
final class lib_test extends \advanced_testcase {
    /**
     * Updating replaces questions, criteria (from the JS JSON fields) and linked materials.
     */
    public function test_update_instance_replaces_children(): void {
        global $CFG, $DB;
        require_once($CFG->dirroot . '/mod/airagassign/lib.php');
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $m1 = $this->getDataGenerator()->create_module('airagmaterial', ['course' => $course->id]);
        $m2 = $this->getDataGenerator()->create_module('airagmaterial', ['course' => $course->id]);
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id, 'assignmode' => 'quiz', 'questions' => ['Old?'],
            'criterionname' => ['Old'], 'criterionmaxscore' => [5], 'materials' => [$m1->id],
        ]);

        $data = $DB->get_record('airagassign', ['id' => $assign->id]);
        $data->instance = $assign->id;
        $data->coursemodule = $assign->cmid;
        $data->questions_json = json_encode(['New one?', ' ', 'New two?']);
        $data->criteria_json = json_encode([['name' => 'Depth', 'desc' => 'Deep', 'maxscore' => 7]]);
        $data->materials = [$m2->id];
        $this->assertTrue(airagassign_update_instance($data));

        $this->assertSame(['New one?', 'New two?'], array_values($DB->get_fieldset_select('airagassign_questions',
            'questiontext', 'assignid = ? ORDER BY sortorder', [$assign->id])));
        $criteria = array_values($DB->get_records('airagassign_criteria', ['assignid' => $assign->id]));
        $this->assertCount(1, $criteria);
        $this->assertSame(['Depth', 'Deep'], [$criteria[0]->name, $criteria[0]->description]);
        $this->assertEquals(7, $criteria[0]->maxscore);
        $this->assertEquals([$m2->id], $DB->get_fieldset_select('airagassign_materials', 'materialid',
            'assignid = ?', [$assign->id]));
    }
}
