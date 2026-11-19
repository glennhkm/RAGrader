<?php
// This file is part of Moodle - https://moodle.org/
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
// along with Moodle.  If not, see <https://www.gnu.org/licenses/>.

/**
 * Plugin version and other meta-data are defined here.
 *
 * RAG-based Assignment AI grading plugin.
 * Uses RAG (Retrieval-Augmented Generation) for contextual essay grading.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$plugin->component = 'local_assign_ai_rag';
$plugin->release = '1.1.2';
$plugin->version = 2026071902;
$plugin->requires = 2024100700;
$plugin->maturity = MATURITY_STABLE;
$plugin->dependencies = [
    'aiprovider_rag' => 2026071901,
];
