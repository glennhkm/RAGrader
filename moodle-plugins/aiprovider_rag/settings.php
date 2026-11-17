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
 * Plugin administration pages are defined here.
 *
 * @package     aiprovider_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

use core_ai\admin\admin_settingspage_provider;

defined('MOODLE_INTERNAL') || die();

// Moodle 4.5 stores one global provider configuration. Moodle 5.0+ stores
// provider instances and obtains these fields through db/hooks.php.
$legacyproviderconfig = !(new \ReflectionMethod(\core_ai\provider::class, 'get_action_list'))->isStatic();

if ($hassiteconfig && $legacyproviderconfig) {
    // Provider specific settings heading.
    $settings = new admin_settingspage_provider(
        'aiprovider_rag',
        new lang_string('pluginname', 'aiprovider_rag'),
        'moodle/site:config',
        true,
    );

    $settings->add(new admin_setting_heading(
        'aiprovider_rag/general',
        new lang_string('settings', 'core'),
        '',
    ));

    // RAG Server URL.
    $settings->add(new admin_setting_configtext(
        'aiprovider_rag/serverurl',
        get_string('serverurl', 'aiprovider_rag'),
        get_string('serverurl_desc', 'aiprovider_rag'),
        'http://localhost:8000',
        PARAM_URL,
    ));

    // API Key (optional).
    $settings->add(new admin_setting_configpasswordunmask(
        'aiprovider_rag/apikey',
        get_string('apikey', 'aiprovider_rag'),
        get_string('apikey_desc', 'aiprovider_rag'),
        '',
    ));

    // Timeout.
    $settings->add(new admin_setting_configtext(
        'aiprovider_rag/timeout',
        get_string('timeout', 'aiprovider_rag'),
        get_string('timeout_desc', 'aiprovider_rag'),
        120,
        PARAM_INT,
    ));

    // Debug.
    $settings->add(new admin_setting_configcheckbox(
        'aiprovider_rag/debug',
        get_string('debug', 'aiprovider_rag'),
        get_string('debug_desc', 'aiprovider_rag'),
        0,
    ));
}
