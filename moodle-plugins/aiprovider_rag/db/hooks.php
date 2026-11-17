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
 * Hook listener callbacks for the RAG AI provider.
 *
 * @package    aiprovider_rag
 * @copyright  2025 Glenn H. K. M.
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$callbacks = [];

// Provider instances and their configuration form were introduced in Moodle
// 5.0. Moodle 4.5 uses settings.php instead and does not define this hook.
if (class_exists(\core_ai\hook\after_ai_provider_form_hook::class)) {
    $callbacks[] = [
        'hook' => \core_ai\hook\after_ai_provider_form_hook::class,
        'callback' => \aiprovider_rag\hook_listener::class . '::set_form_definition_for_aiprovider_rag',
    ];
}
