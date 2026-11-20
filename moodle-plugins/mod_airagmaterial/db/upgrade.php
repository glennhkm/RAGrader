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
 * Upgrade steps for AI RAG Material module.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

function xmldb_airagmaterial_upgrade($oldversion) {
    global $CFG;

    if ($oldversion < 2025010101) {
        // Capabilities are re-synced automatically on upgrade.
        upgrade_mod_savepoint(true, 2025010101, 'airagmaterial');
    }

    if ($oldversion < 2026112100) {
        // Vectors are now owned per material (airagmaterial:{id}). Re-vectorize every
        // material in the background; no HTTP call is made during the upgrade itself.
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');
        $queued = airagmaterial_queue_owner_migration();
        if ($queued > 0) {
            \core\notification::info(get_string('upgrade_revectorize_notice', 'mod_airagmaterial', $queued));
        }
        upgrade_mod_savepoint(true, 2026112100, 'airagmaterial');
    }

    return true;
}
