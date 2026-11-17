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
 * Index page listing all AI RAG Material instances in a course.
 *
 * @package    mod_airagmaterial
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

$id = required_param('id', PARAM_INT); // Course ID.
$course = get_course($id);

require_login($course);
$PAGE->set_url('/mod/airagmaterial/index.php', ['id' => $id]);
$PAGE->set_pagelayout('incourse');
$PAGE->set_title(get_string('modulenameplural', 'airagmaterial'));
$PAGE->set_heading($course->fullname);

echo $OUTPUT->header();
echo $OUTPUT->heading(get_string('modulenameplural', 'airagmaterial'));

$materials = get_all_instances_in_course('airagmaterial', $course);

if (empty($materials)) {
    notice(get_string('nofiles', 'airagmaterial'), new moodle_url('/course/view.php', ['id' => $course->id]));
}

$table = new html_table();
$table->head = ['Name', 'Status', 'Documents', 'Chunks', 'Last Processed'];
$table->align = ['left', 'center', 'center', 'center', 'center'];

foreach ($materials as $material) {
    $link = html_writer::link(
        new moodle_url('/mod/airagmaterial/view.php', ['id' => $material->coursemodule]),
        format_string($material->name)
    );

    $statusclass = 'badge ';
    switch ($material->vectorize_status) {
        case 'completed':
            $statusclass .= 'badge-success bg-success';
            break;
        case 'processing':
            $statusclass .= 'badge-warning bg-warning';
            break;
        case 'failed':
            $statusclass .= 'badge-danger bg-danger';
            break;
        default:
            $statusclass .= 'badge-secondary bg-secondary';
    }
    $status = html_writer::span(
        get_string('status_' . $material->vectorize_status, 'airagmaterial'),
        $statusclass
    );

    $lastprocessed = $material->last_vectorized > 0
        ? userdate($material->last_vectorized)
        : get_string('never', 'airagmaterial');

    $table->data[] = [
        $link,
        $status,
        $material->documents_loaded,
        $material->chunks_created,
        $lastprocessed,
    ];
}

echo html_writer::table($table);
echo $OUTPUT->footer();
