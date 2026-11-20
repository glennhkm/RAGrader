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

use mod_airagmaterial\local\http_factory;

/**
 * Tests for restoring (duplicating) an AI RAG Material activity.
 *
 * @package    mod_airagmaterial
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \restore_airagmaterial_activity_structure_step
 */
final class restore_test extends \advanced_testcase {
    /**
     * Duplicating a material creates a new instance with its files and tracking rows, pending re-vectorization.
     */
    public function test_duplicate_restores_instance_files_and_rows(): void {
        global $CFG, $DB;
        require_once($CFG->dirroot . '/course/lib.php');
        $this->resetAfterTest();
        $this->setAdminUser();

        $course = $this->getDataGenerator()->create_course();
        $gen = $this->getDataGenerator()->get_plugin_generator('mod_airagmaterial');
        $material = $gen->create_instance(['course' => $course->id, 'name' => 'Week 1',
            'vectorize_status' => 'completed']);
        $file = $gen->create_file($material, 'notes.txt', 'lecture notes');
        $DB->insert_record('airagmaterial_files', (object)[
            'materialid' => $material->id, 'filename' => 'notes.txt', 'filesize' => $file->get_filesize(),
            'contenthash' => $file->get_contenthash(), 'vectorized' => 1, 'chunks_count' => 3,
            'timecreated' => time(),
        ]);

        // Restore never talks to the RAG backend.
        $factory = $this->createMock(http_factory::class);
        $factory->expects($this->never())->method('create');
        \core\di::set(http_factory::class, $factory);

        $newcm = duplicate_module($course, get_fast_modinfo($course)->get_cm($material->cmid));

        $this->assertSame('airagmaterial', $newcm->modname);
        $newid = (int)$newcm->instance;
        $this->assertNotEquals((int)$material->id, $newid);
        $restored = $DB->get_record('airagmaterial', ['id' => $newid], '*', MUST_EXIST);
        $this->assertEquals($course->id, $restored->course);
        $this->assertStringStartsWith('Week 1', $restored->name);
        // Vectors are not portable: the copy waits for re-vectorization under its own owner id.
        $this->assertSame('pending', $restored->vectorize_status);

        // The material file is mapped into the new module context.
        $newcontext = \context_module::instance($newcm->id);
        $files = get_file_storage()->get_area_files($newcontext->id, 'mod_airagmaterial', 'materials', 0,
            'filename', false);
        $this->assertSame(['notes.txt'], array_values(array_map(fn($f) => $f->get_filename(), $files)));
        $this->assertSame($file->get_contenthash(), reset($files)->get_contenthash());

        // Tracking rows belong to the new instance and are not marked vectorized.
        $rows = $DB->get_records('airagmaterial_files', ['materialid' => $newid]);
        $this->assertCount(1, $rows);
        $row = reset($rows);
        $this->assertSame('notes.txt', $row->filename);
        $this->assertEquals(0, $row->vectorized);
        // The original is untouched.
        $this->assertSame('completed', $DB->get_field('airagmaterial', 'vectorize_status', ['id' => $material->id]));
        $this->assertSame(1, $DB->count_records('airagmaterial_files', ['materialid' => $material->id]));
    }
}
