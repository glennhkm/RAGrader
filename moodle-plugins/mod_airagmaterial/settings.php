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
 * Admin settings for AI RAG Material module.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

if ($ADMIN->fulltree) {
    $settings->add(new admin_setting_configtext(
        'mod_airagmaterial/serverurl',
        get_string('serverurl', 'airagmaterial'),
        get_string('serverurl_desc', 'airagmaterial'),
        'http://127.0.0.1:8000',
        PARAM_URL
    ));

    $settings->add(new admin_setting_configpasswordunmask(
        'mod_airagmaterial/apikey',
        get_string('apikey', 'airagmaterial'),
        get_string('apikey_desc', 'airagmaterial'),
        ''
    ));
}
