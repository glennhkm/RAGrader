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
20:  * Grading areas definition for AI RAG Assignment module.
21:  *
22:  * @package    mod_airagassign
23:  * @copyright  2026 Glenn HKM
24:  * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
25:  */

defined('MOODLE_INTERNAL') || die();

$areas = [
    'submissions' => [
        'title' => get_string('submissions', 'mod_airagassign'),
        'description' => get_string('submissions_help', 'mod_airagassign'),
    ]
];
