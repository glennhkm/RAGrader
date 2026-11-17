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
 * This plugin provides RAG (Retrieval-Augmented Generation) based AI
 * capabilities for Moodle, specifically designed for essay grading
 * with course material context.
 *
 * @package     aiprovider_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$plugin->component = 'aiprovider_rag';
$plugin->release = '1.1.1';
$plugin->version = 2026071901;
$plugin->requires = 2024100700; // Moodle 4.5+
$plugin->maturity = MATURITY_STABLE;
