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
 * Tests for the 1.2.0 upgrade step.
 *
 * @package    mod_airagmaterial
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     ::xmldb_airagmaterial_upgrade
 */
final class upgrade_test extends \advanced_testcase {
    public function test_upgrade_queues_revectorization_without_http(): void {
        global $CFG, $DB;
        require_once($CFG->libdir . '/upgradelib.php');
        require_once($CFG->dirroot . '/mod/airagmaterial/db/upgrade.php');
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $gen = $this->getDataGenerator()->get_plugin_generator('mod_airagmaterial');
        $material = $gen->create_instance(['course' => $course->id, 'vectorize_status' => 'completed']);
        $gen->create_file($material, 'a.txt', 'alpha');
        $DB->delete_records('task_adhoc');

        // Any HTTP attempt would hit the real factory; fail loudly instead.
        $factory = $this->createMock(\mod_airagmaterial\local\http_factory::class);
        $factory->expects($this->never())->method('create');
        \core\di::set(\mod_airagmaterial\local\http_factory::class, $factory);

        // Pretend the previous release is installed so the savepoint check passes.
        set_config('version', 2026071902, 'mod_airagmaterial');

        $this->assertTrue(xmldb_airagmaterial_upgrade(2026071902));

        $this->assertSame('queued', $DB->get_field('airagmaterial', 'vectorize_status', ['id' => $material->id]));
        $this->assertSame(1, $DB->count_records('task_adhoc'));
    }
}
