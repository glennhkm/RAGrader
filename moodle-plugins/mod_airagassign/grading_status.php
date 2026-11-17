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
 * AJAX status endpoint for airagassign grading queue.
 *
 * Returns JSON with counts of submissions in each status for this assignment.
 * Used by the front-end polling loop on view.php to auto-refresh
 * when background grading tasks complete.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

define('AJAX_SCRIPT', true);

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

$id = required_param('id', PARAM_INT); // Course-module ID.

$cm     = get_coursemodule_from_id('airagassign', $id, 0, false, MUST_EXIST);
$course = get_course($cm->course);
$assign = $DB->get_record('airagassign', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_capability('mod/airagassign:grade', $context);

$grading_count     = (int)$DB->count_records_select('airagassign_submissions',
    "assignid = :aid AND status = 'grading'", ['aid' => $assign->id]);
$suggested_count   = (int)$DB->count_records_select('airagassign_submissions',
    "assignid = :aid AND status = 'ai_suggested'", ['aid' => $assign->id]);
$graded_count      = (int)$DB->count_records_select('airagassign_submissions',
    "assignid = :aid AND status = 'graded'", ['aid' => $assign->id]);
$submitted_count   = (int)$DB->count_records_select('airagassign_submissions',
    "assignid = :aid AND status = 'submitted'", ['aid' => $assign->id]);
$failed_count      = (int)$DB->count_records_select('airagassign_submissions',
    "assignid = :aid AND status = 'grading_failed'", ['aid' => $assign->id]);

header('Content-Type: application/json');
echo json_encode([
    'grading'      => $grading_count,
    'ai_suggested' => $suggested_count,
    'graded'       => $graded_count,
    'submitted'    => $submitted_count,
    'failed'       => $failed_count,
    'busy'         => $grading_count > 0,
]);
