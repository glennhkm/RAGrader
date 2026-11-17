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

/**
 * Index page listing all AI RAG Assignments in a course.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

// Dynamic Moodle config path resolver to support symlinked directories and public folder layouts
$configpath = null;
$candidates = [
    __DIR__ . '/../../config.php',
    __DIR__ . '/../../../config.php',
    __DIR__ . '/../moodle/config.php',
];
if (isset($_SERVER['SCRIPT_FILENAME'])) {
    $dir = dirname($_SERVER['SCRIPT_FILENAME']);
    for ($i = 0; $i < 5; $i++) {
        $candidates[] = $dir . '/config.php';
        $dir = dirname($dir);
    }
}
foreach ($candidates as $path) {
    if (file_exists($path)) {
        $configpath = realpath($path);
        break;
    }
}
if ($configpath) {
    require_once($configpath);
} else {
    require_once(__DIR__ . '/../../config.php'); // Fallback
}

$id = required_param('id', PARAM_INT);
$course = get_course($id);

require_login($course);
$PAGE->set_url('/mod/airagassign/index.php', ['id' => $id]);
$PAGE->set_pagelayout('incourse');
$PAGE->set_title(get_string('modulenameplural', 'airagassign'));
$PAGE->set_heading($course->fullname);

echo $OUTPUT->header();
echo $OUTPUT->heading(get_string('modulenameplural', 'airagassign'));

$assigns = get_all_instances_in_course('airagassign', $course);

if (empty($assigns)) {
    notice('No AI RAG Assignments found in this course.',
        new moodle_url('/course/view.php', ['id' => $course->id]));
}

$table = new html_table();
$table->head = ['Name', 'Mode', 'Max Grade', 'Due Date'];
$table->align = ['left', 'center', 'center', 'center'];

foreach ($assigns as $a) {
    $link = html_writer::link(
        new moodle_url('/mod/airagassign/view.php', ['id' => $a->coursemodule]),
        format_string($a->name)
    );

    $mode = ($a->assignmode === 'quiz')
        ? html_writer::span(get_string('mode_quiz', 'airagassign'), 'badge bg-primary')
        : html_writer::span(get_string('mode_essay', 'airagassign'), 'badge bg-info');

    $duedate = ($a->duedate > 0) ? userdate($a->duedate) : '-';

    $table->data[] = [$link, $mode, format_float($a->maximumgrade, 2), $duedate];
}

echo html_writer::table($table);
echo $OUTPUT->footer();
