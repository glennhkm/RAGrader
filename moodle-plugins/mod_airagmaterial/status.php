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
 * AJAX status endpoint for airagmaterial vectorization queue.
 *
 * Returns JSON with the current vectorize_status of the material.
 * Used by the front-end polling loop on view.php to auto-refresh
 * when a background vectorization task completes.
 *
 * @package    mod_airagmaterial
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

$cm       = get_coursemodule_from_id('airagmaterial', $id, 0, false, MUST_EXIST);
$course   = get_course($cm->course);
$material = $DB->get_record('airagmaterial', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_capability('mod/airagmaterial:manage', $context);

header('Content-Type: application/json');
echo json_encode([
    'status'         => $material->vectorize_status,
    'chunks'         => (int)$material->chunks_created,
    'documents'      => (int)$material->documents_loaded,
    'last_vectorized'=> (int)$material->last_vectorized,
    'error'          => $material->vectorize_error ?? '',
    'busy'           => in_array($material->vectorize_status, ['queued', 'processing']),
]);
