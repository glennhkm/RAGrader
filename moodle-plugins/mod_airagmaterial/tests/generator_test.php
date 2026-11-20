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

namespace mod_airagmaterial;

/**
 * Smoke test for the mod_airagmaterial data generator.
 *
 * @package    mod_airagmaterial
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagmaterial_generator
 */
final class generator_test extends \advanced_testcase {
    /**
     * An instance is created with a pending vectorization status.
     */
    public function test_create_instance(): void {
        global $DB;
        $this->resetAfterTest();

        $course = $this->getDataGenerator()->create_course();
        $material = $this->getDataGenerator()->create_module('airagmaterial', ['course' => $course->id]);

        $record = $DB->get_record('airagmaterial', ['id' => $material->id], '*', MUST_EXIST);
        $this->assertEquals($course->id, $record->course);
        $this->assertSame('pending', $record->vectorize_status);
    }

    /**
     * A file can be attached in the area read by airagmaterial_get_uploaded_files().
     */
    public function test_create_file(): void {
        global $CFG;
        $this->resetAfterTest();
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');

        $course = $this->getDataGenerator()->create_course();
        $material = $this->getDataGenerator()->create_module('airagmaterial', ['course' => $course->id]);
        $generator = $this->getDataGenerator()->get_plugin_generator('mod_airagmaterial');

        $file = $generator->create_file($material, 'notes.txt', 'Hello materials');

        $files = airagmaterial_get_uploaded_files(\context_module::instance($material->cmid)->id);
        $this->assertCount(1, $files);
        $this->assertSame('notes.txt', $file->get_filename());
        $this->assertSame('Hello materials', $file->get_content());
    }
}
