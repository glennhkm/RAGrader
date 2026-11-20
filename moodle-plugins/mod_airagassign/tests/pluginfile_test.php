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
 * Access checks for files served by airagassign_pluginfile().
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     ::airagassign_pluginfile
 */
final class pluginfile_test extends \advanced_testcase {
    /**
     * Load lib.php.
     */
    public static function setUpBeforeClass(): void {
        global $CFG;
        parent::setUpBeforeClass();
        require_once($CFG->dirroot . '/mod/airagassign/lib.php');
    }

    /**
     * Create an assignment with a manual reference file plus an enrolled student and teacher.
     *
     * @return array [course, cmid, context, student, teacher]
     */
    private function setup_assignment(): array {
        $this->resetAfterTest();
        $generator = $this->getDataGenerator();
        $course = $generator->create_course();
        $assign = $generator->create_module('airagassign', ['course' => $course->id]);
        $context = \context_module::instance($assign->cmid);
        get_file_storage()->create_file_from_string([
            'contextid' => $context->id, 'component' => 'mod_airagassign', 'filearea' => 'manualfile',
            'itemid' => 0, 'filepath' => '/', 'filename' => 'key.txt',
        ], 'model answer key');
        $student = $generator->create_and_enrol($course, 'student');
        $teacher = $generator->create_and_enrol($course, 'editingteacher');
        return [$course, (int)$assign->cmid, $context, $student, $teacher];
    }

    /**
     * Log in as a user and return the course module as that user sees it.
     *
     * Modinfo is per user: a cm_info fetched before setUser() is not visible to the
     * logged-in user, and require_login() would redirect.
     *
     * @param \stdClass $course Course.
     * @param int $cmid Course module id.
     * @param \stdClass $user User to log in as.
     * @return \cm_info
     */
    private function login_as(\stdClass $course, int $cmid, \stdClass $user): \cm_info {
        $this->setUser($user);
        return get_fast_modinfo($course, $user->id)->get_cm($cmid);
    }

    /**
     * An enrolled student cannot download the manual reference file (the answer key).
     */
    public function test_student_cannot_download_manualfile(): void {
        [$course, $cmid, $context, $student] = $this->setup_assignment();
        $cm = $this->login_as($course, $cmid, $student);

        $this->expectException(\required_capability_exception::class);
        airagassign_pluginfile($course, $cm, $context, 'manualfile', [0, 'key.txt'], true);
    }

    /**
     * A grader passes the capability check; a missing file is then simply not found.
     *
     * The existing file is not requested because send_stored_file() ends the request.
     */
    public function test_teacher_passes_manualfile_access_check(): void {
        [$course, $cmid, $context, , $teacher] = $this->setup_assignment();
        $cm = $this->login_as($course, $cmid, $teacher);

        $this->assertTrue(has_capability('mod/airagassign:grade', $context));
        $this->assertFalse(airagassign_pluginfile($course, $cm, $context, 'manualfile', [0, 'missing.txt'], true));
    }

    /**
     * Other file areas keep their behaviour: nothing is served, for students too.
     */
    public function test_other_areas_are_not_served(): void {
        [$course, $cmid, $context, $student] = $this->setup_assignment();
        $cm = $this->login_as($course, $cmid, $student);

        $this->assertFalse(airagassign_pluginfile($course, $cm, $context, 'intro', [0, 'key.txt'], true));
    }
}
