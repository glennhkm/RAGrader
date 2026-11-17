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
 * Module form for AI RAG Assignment.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

require_once($CFG->dirroot . '/course/moodleform_mod.php');

/**
 * Form for adding/editing AI RAG Assignment.
 */
class mod_airagassign_mod_form extends moodleform_mod {

    public function definition() {
        global $CFG, $DB, $COURSE;

        $mform = $this->_form;

        // ==================== GENERAL ====================
        $mform->addElement('header', 'general', get_string('general', 'form'));

        $mform->addElement('text', 'name', get_string('assignmentname', 'airagassign'),
            ['size' => '64', 'placeholder' => get_string('assignmentname_placeholder', 'airagassign')]);
        $mform->setType('name', PARAM_TEXT);
        $mform->addRule('name', null, 'required', null, 'client');
        $mform->addRule('name', get_string('maximumchars', '', 255), 'maxlength', 255, 'client');
        $mform->addHelpButton('name', 'assignmentname', 'airagassign');

        $this->standard_intro_elements();

        // Assignment mode.
        $mform->addElement('select', 'assignmode', get_string('assignmentmode', 'airagassign'), [
            'quiz'  => get_string('mode_quiz', 'airagassign'),
            'essay' => get_string('mode_essay', 'airagassign'),
        ]);
        $mform->addHelpButton('assignmode', 'assignmentmode', 'airagassign');

        // Grade configuration is handled by Moodle native grade module standard elements below.

        // Open date.
        $mform->addElement('date_time_selector', 'opendate', get_string('opendate', 'airagassign'), ['optional' => true]);
        $mform->addHelpButton('opendate', 'opendate', 'airagassign');
        $mform->setDefault('opendate', 0);

        // Due date.
        $mform->addElement('date_time_selector', 'duedate', get_string('duedate', 'airagassign'), ['optional' => true]);
        $mform->addHelpButton('duedate', 'duedate', 'airagassign');

        // Allow late submissions.
        $mform->addElement('advcheckbox', 'allowlate', get_string('allowlatesubmission', 'airagassign'));
        $mform->setDefault('allowlate', 0);

        // Date order hint (shown when both dates are enabled).
        $mform->addElement('static', 'dateorder_hint', '',
            html_writer::tag('div',
                '📅 ' . get_string('dateorder_hint', 'airagassign'),
                ['class' => 'alert alert-warning py-2 mb-0', 'id' => 'airagassign-dateorder-hint', 'style' => 'display:none']
            )
        );
        // JS: show warning when open > due
        $mform->addElement('static', 'dateorder_script', '', <<<DATEHTML
            <script>
            (function() {
                function getTs(prefix) {
                    // Moodle date_time_selector uses selects: fieldname[year], [month], [day], [hour], [minute]
                    var d = document;
                    var y  = d.querySelector('[name="' + prefix + '[year]"]');
                    var mo = d.querySelector('[name="' + prefix + '[month]"]');
                    var dy = d.querySelector('[name="' + prefix + '[day]"]');
                    var h  = d.querySelector('[name="' + prefix + '[hour]"]');
                    var mi = d.querySelector('[name="' + prefix + '[minute]"]');
                    var en = d.querySelector('[name="' + prefix + '[enabled]"]');
                    if (!y || !mo || !dy) return 0;
                    if (en && !en.checked) return 0;
                    return Date.UTC(
                        parseInt(y.value), parseInt(mo.value) - 1, parseInt(dy.value),
                        h ? parseInt(h.value) : 0, mi ? parseInt(mi.value) : 0
                    );
                }
                function checkDates() {
                    var open = getTs('opendate');
                    var due  = getTs('duedate');
                    var hint = document.getElementById('airagassign-dateorder-hint');
                    if (!hint) return;
                    if (open > 0 && due > 0 && open >= due) {
                        hint.style.display = '';
                    } else {
                        hint.style.display = 'none';
                    }
                }
                document.addEventListener('change', function(e) {
                    var n = e.target && e.target.name || '';
                    if (n.indexOf('opendate') !== -1 || n.indexOf('duedate') !== -1) {
                        checkDates();
                    }
                });
                setTimeout(checkDates, 400);
            })();
            </script>
        DATEHTML);

        // ==================== MATERIALS ====================
        $mform->addElement('header', 'materialshdr', get_string('materialsheader', 'airagassign'));
        $mform->setExpanded('materialshdr');

        $materials = $DB->get_records('airagmaterial', ['course' => $COURSE->id], 'name ASC');
        if (empty($materials)) {
            $mform->addElement('static', 'nomaterials', '', html_writer::tag('div',
                get_string('nomaterials', 'airagassign'),
                ['class' => 'alert alert-warning']
            ));
        } else {
            $materoptions = [];
            foreach ($materials as $mat) {
                $statuslabel = ($mat->vectorize_status === 'completed')
                    ? ' ✓ [vectorized]'
                    : ' ⚠ [' . ($mat->vectorize_status ?: 'not vectorized') . ']';
                $materoptions[$mat->id] = format_string($mat->name) . $statuslabel;
            }

            // Interactive multi-select with search (Moodle autocomplete element).
            $mform->addElement('autocomplete', 'materials',
                get_string('selectmaterials', 'airagassign'),
                $materoptions,
                [
                    'multiple'          => true,
                    'noselectionstring' => get_string('selectmaterials_placeholder', 'airagassign'),
                ]
            );
            $mform->addHelpButton('materials', 'selectmaterials', 'airagassign');
            $mform->addElement('static', 'materials_hint', '',
                html_writer::tag('small', get_string('materials_hint', 'airagassign'), ['class' => 'text-muted'])
            );
        }

        // Upload manual files (model answers / references)
        $mform->addElement('filepicker', 'manualfile', get_string('manualfile', 'airagassign'), null, [
            'maxbytes' => 50 * 1024 * 1024,
            'accepted_types' => ['.pdf', '.pptx', '.docx', '.txt'],
        ]);
        $mform->addHelpButton('manualfile', 'manualfile', 'airagassign');

        // Rubric elements moved directly inside the native Grade section below.

        // ==================== ESSAY MODE ====================
        $mform->addElement('header', 'essayhdr', get_string('essayheader', 'airagassign'));
        $mform->setExpanded('essayhdr');

        $mform->addElement('static', 'essayprompt_hint', '',
            html_writer::tag('div',
                '✏️ ' . get_string('essayprompt_required_hint', 'airagassign'),
                ['class' => 'alert alert-info py-2 mb-2']
            )
        );
        $mform->hideIf('essayprompt_hint', 'assignmode', 'eq', 'quiz');

        $mform->addElement('textarea', 'essayprompt', get_string('essayprompt', 'airagassign'),
            ['rows' => 5, 'cols' => 80, 'placeholder' => get_string('essayprompt_placeholder', 'airagassign')]);
        $mform->setType('essayprompt', PARAM_TEXT);
        $mform->addHelpButton('essayprompt', 'essayprompt', 'airagassign');
        $mform->hideIf('essayprompt', 'assignmode', 'eq', 'quiz');

        $mform->addElement('text', 'minwords', get_string('minwords', 'airagassign'),
            ['size' => '5', 'placeholder' => '0']);
        $mform->setType('minwords', PARAM_INT);
        $mform->setDefault('minwords', 0);
        $mform->addElement('static', 'minmaxwords_hint', '',
            html_writer::tag('small', get_string('minmaxwords_hint', 'airagassign'), ['class' => 'text-muted'])
        );
        $mform->hideIf('minwords', 'assignmode', 'eq', 'quiz');
        $mform->hideIf('minmaxwords_hint', 'assignmode', 'eq', 'quiz');

        $mform->addElement('text', 'maxwords', get_string('maxwords', 'airagassign'),
            ['size' => '5', 'placeholder' => '0']);
        $mform->setType('maxwords', PARAM_INT);
        $mform->setDefault('maxwords', 0);
        $mform->hideIf('maxwords', 'assignmode', 'eq', 'quiz');

        // ==================== QUIZ MODE ====================
        $mform->addElement('header', 'quizhdr', get_string('questionsheader', 'airagassign'));
        $mform->setExpanded('quizhdr');

        // Build questions: prefer POST (validation re-render) > DB (edit) > defaults (new).
        $initialquestions = [];
        $postedquestions  = optional_param_array('questions', null, PARAM_TEXT);
        if ($postedquestions !== null) {
            foreach ($postedquestions as $i => $qtext) {
                $initialquestions[(int)$i] = $qtext;
            }
        } else if ($this->current->instance) {
            $dbquestions = $DB->get_records('airagassign_questions', ['assignid' => $this->current->instance], 'sortorder ASC');
            foreach (array_values($dbquestions) as $idx => $q) {
                $initialquestions[$idx] = $q->questiontext;
            }
        }
        if (empty($initialquestions)) {
            $initialquestions = ['', '', ''];
        }

        $mform->addElement('hidden', 'questions_json', '');
        $mform->setType('questions_json', PARAM_RAW);

        $mform->addElement('static', 'questions_table', '', $this->_build_questions_list($initialquestions));
        $mform->hideIf('questions_table', 'assignmode', 'eq', 'essay');

        // Hide entire sections based on mode.
        $mform->hideIf('quizhdr', 'assignmode', 'eq', 'essay');
        $mform->hideIf('essayhdr', 'assignmode', 'eq', 'quiz');

        // ==================== STANDARD ELEMENTS ====================
        $this->standard_grading_coursemodule_elements();
        if ($mform->elementExists('modstandardgrade')) {
            $mform->setExpanded('modstandardgrade');
        }

        // Add the plugin's built-in custom rubric option, and remove Marking
        // guide. AI RAG grading supports simple grading, Moodle native Rubric,
        // and this plugin's custom rubric only.
        if ($mform->elementExists('advancedgradingmethod_submissions')) {
            $el = $mform->getElement('advancedgradingmethod_submissions');
            foreach (['guide', 'markingguide'] as $unsupportedmethod) {
                $this->remove_select_option_safely($el, $unsupportedmethod);
            }
            $el->addOption(get_string('rubricmode_custom', 'airagassign'), 'custom');
            $this->order_grading_method_options($el);
            if (empty($this->current->instance) && method_exists($el, 'setSelected')) {
                $el->setSelected('custom');
            }
        }
        $mform->setDefault('advancedgradingmethod_submissions', 'custom');


        // Move dynamic Custom Rubric components inside the standard Grade section.
        $mform->addElement('static', 'moodlerubric_info', '', html_writer::tag('div',
            'ℹ️ ' . get_string('moodlerubric_info_text', 'airagassign'),
            ['class' => 'alert alert-info py-2 mb-0']
        ));
        $mform->hideIf('moodlerubric_info', 'advancedgradingmethod_submissions', 'eq', 'custom');
        $mform->hideIf('moodlerubric_info', 'advancedgradingmethod_submissions', 'eq', '');
        $mform->hideIf('rubric_table', 'advancedgradingmethod_submissions', 'neq', 'custom');

        // Build criteria: prefer POST (validation re-render) > DB (edit) > defaults (new).
        $initialcriteria  = [];
        $postedcnames = optional_param_array('criterionname', null, PARAM_TEXT);
        if ($postedcnames !== null) {
            $posteddesc   = optional_param_array('criteriondesc', [], PARAM_TEXT);
            $postedscores = optional_param_array('criterionmaxscore', [], PARAM_RAW);
            foreach ($postedcnames as $i => $cname) {
                $initialcriteria[(int)$i] = [
                    'name'     => $cname,
                    'desc'     => $posteddesc[$i] ?? '',
                    'maxscore' => $postedscores[$i] ?? '',
                ];
            }
        } else if ($this->current->instance) {
            $dbcriteria = $DB->get_records('airagassign_criteria', ['assignid' => $this->current->instance], 'sortorder ASC');
            foreach (array_values($dbcriteria) as $idx => $c) {
                $initialcriteria[$idx] = ['name' => $c->name, 'desc' => $c->description, 'maxscore' => $c->maxscore];
            }
        }
        if (empty($initialcriteria)) {
            $initialcriteria = [
                ['name' => get_string('defaultcriterion_relevance',    'airagassign'), 'desc' => get_string('defaultcriterion_relevance_desc',    'airagassign'), 'maxscore' => 40],
                ['name' => get_string('defaultcriterion_accuracy',     'airagassign'), 'desc' => get_string('defaultcriterion_accuracy_desc',     'airagassign'), 'maxscore' => 35],
                ['name' => get_string('defaultcriterion_completeness', 'airagassign'), 'desc' => get_string('defaultcriterion_completeness_desc', 'airagassign'), 'maxscore' => 25],
            ];
        }

        // Hidden fields that carry the dynamic table data through Moodle's form system.
        $mform->addElement('hidden', 'criteria_json', '');
        $mform->setType('criteria_json', PARAM_RAW);

        $mform->addElement('static', 'rubric_table', '', $this->_build_rubric_table($initialcriteria));

        $this->standard_coursemodule_elements();
        $this->add_action_buttons();
    }

    /**
     * Pre-fill form with existing data when editing.
     * Criteria/questions are now handled in definition() — only materials needed here.
     *
     * @param array $defaultvalues Default values
     */
    public function data_preprocessing(&$defaultvalues) {
        global $DB;

        if ($this->current->instance) {
            // Load linked materials for the autocomplete element.
            $linked = $DB->get_records('airagassign_materials', ['assignid' => $this->current->instance], '', 'materialid');
            $defaultvalues['materials'] = array_keys($linked);

            // Pre-fill grade from maximumgrade.
            if (isset($this->current->maximumgrade)) {
                $defaultvalues['grade'] = $this->current->maximumgrade;
            }

            // Keep the selected grading method stable when reopening settings.
            // Moodle uses an empty value for simple direct grading; this plugin
            // stores that explicitly as rubricmode=simple.
            $rubricmode = $this->current->rubricmode ?? 'custom';
            if ($rubricmode === 'custom') {
                $defaultvalues['advancedgradingmethod_submissions'] = 'custom';
            } else if ($rubricmode === 'moodle') {
                $defaultvalues['advancedgradingmethod_submissions'] = 'rubric';
            } else {
                $defaultvalues['advancedgradingmethod_submissions'] = '';
            }
        } else {
            $defaultvalues['advancedgradingmethod_submissions'] = 'custom';
        }

        // Prepare draft area for manual file upload.
        $draftitemid = file_get_submitted_draft_itemid('manualfile');
        $contextid = 0;
        if ($this->current->instance) {
            $context = context_module::instance($this->current->coursemodule);
            $contextid = $context->id;
        }
        file_prepare_draft_area(
            $draftitemid,
            $contextid,
            'mod_airagassign',
            'manualfile',
            0,
            ['subdirs' => false, 'maxfiles' => 1]
        );
        $defaultvalues['manualfile'] = $draftitemid;
    }

    /**
     * Intercept form data submission.
     * Maps native grade to maximumgrade, and maps advancedgradingmethod_submissions
     * to rubricmode while resetting it for Moodle core.
     *
     * @return stdClass|null Form data object
     */
    public function get_data() {
        $data = parent::get_data();
        if ($data) {
            // Map native grade to maximumgrade.
            if (isset($data->grade)) {
                $data->maximumgrade = $data->grade;
            }

            // Intercept advancedgradingmethod_submissions.
            $gradingmethod = $data->advancedgradingmethod_submissions ?? '';
            if ($gradingmethod === 'custom') {
                $data->rubricmode = 'custom';
                // Reset to empty (simple direct grading) so Moodle core doesn't crash on set_active_method().
                $data->advancedgradingmethod_submissions = '';
            } else if ($gradingmethod === 'rubric') {
                $data->rubricmode = 'moodle';
            } else {
                $data->rubricmode = 'simple';
            }
        }
        return $data;
    }

    /**
     * Build interactive rubric HTML table with add/delete rows.
     * Includes real-time sum-vs-max-grade validation feedback.
     *
     * @param array $criteria Array of ['name'=>..., 'desc'=>..., 'maxscore'=>...]
     * @return string HTML
     */
    private function _build_rubric_table(array $criteria): string {
        $nameph   = s(get_string('criterionname_placeholder', 'airagassign'));
        $descph   = s(get_string('criteriondesc_placeholder', 'airagassign'));
        $addlbl   = s(get_string('addcriterion', 'airagassign'));
        $dellbl_s = s(get_string('delete', 'core'));
        $namehdr  = s(get_string('criterionname', 'airagassign'));
        $deschdr  = s(get_string('criteriondesc', 'airagassign'));
        $scorehdr = s(get_string('criterionmaxscore', 'airagassign'));
        $sumhint  = s(get_string('rubric_sumhint', 'airagassign'));
        $reqhint  = s(get_string('rubric_required_hint', 'airagassign'));

        // JS values via json_encode (produces safe double-quoted JS strings).
        $js_nameph    = json_encode(get_string('criterionname_placeholder', 'airagassign'));
        $js_descph    = json_encode(get_string('criteriondesc_placeholder', 'airagassign'));
        $js_dellbl    = json_encode(get_string('delete', 'core'));
        $js_alertmin  = json_encode(get_string('criterion_required_error', 'airagassign'));
        // Real-time validation labels (inline strings — no extra lang keys needed).
        $js_lbl_diff   = json_encode('Selisih');

        $rowshtml = '';
        $nextidx  = 0;
        foreach ($criteria as $i => $c) {
            $name     = s((string)($c['name'] ?? ''));
            $desc     = s((string)($c['desc'] ?? ''));
            $maxscore = s((string)($c['maxscore'] ?? ''));
            $rowshtml .= <<<HTML
            <tr class="airag-rubric-row">
                <td><input type="text" name="criterionname[{$i}]" value="{$name}"
                    placeholder="{$nameph}" class="form-control form-control-sm"></td>
                <td><input type="text" name="criteriondesc[{$i}]" value="{$desc}"
                    placeholder="{$descph}" class="form-control form-control-sm"></td>
                <td><input type="number" name="criterionmaxscore[{$i}]" value="{$maxscore}"
                    placeholder="e.g. 40" min="0" step="any"
                    class="form-control form-control-sm airag-score-input"></td>
                <td class="text-center align-middle">
                    <button type="button" class="btn btn-sm btn-outline-danger airag-del-criterion"
                        title="{$dellbl_s}">&#x2715; {$dellbl_s}</button>
                </td>
            </tr>
            HTML;
            $nextidx = $i + 1;
        }

        return <<<HTML
        <div class="alert alert-info py-2 mb-3">
            <strong>{$sumhint}</strong><br>
            <small class="text-muted">{$reqhint}</small>
        </div>
        <div style="overflow-x:auto">
        <table class="table table-sm table-bordered mb-2">
            <thead class="table-light">
                <tr>
                    <th style="width:29%">{$namehdr} <span class="text-danger">*</span></th>
                    <th style="width:45%">{$deschdr}</th>
                    <th style="width:13%">{$scorehdr} <span class="text-danger">*</span></th>
                    <th style="width:13%"></th>
                </tr>
            </thead>
            <tbody id="airagassign-rubric-body">{$rowshtml}
            </tbody>
        </table>
        </div>
        <div id="airagassign-rubric-summary" class="mb-2"></div>
        <button type="button" class="btn btn-sm btn-outline-primary" id="airagassign-add-criterion">
            + {$addlbl}
        </button>
        <script>
        (function() {
            var idx      = {$nextidx};
            var nameph   = {$js_nameph};
            var descph   = {$js_descph};
            var dellbl   = {$js_dellbl};
            var alertmin = {$js_alertmin};
            var lblMatch = "\u2714 Sesuai dengan nilai maksimum";
            var lblErr   = "\u2716 Harus sama dengan nilai maksimum";
            var lblDiff  = {$js_lbl_diff};

            // ── Real-time rubric score validation ────────────────────────────────
            function updateRubricSummary() {
                // Dual selector: by name (standard) OR by Moodle-generated id (fallback)
                var maxGradeEl = document.querySelector('input[name="grade[modgrade_point]"]')
                              || document.querySelector('#id_grade_modgrade_point');
                var maxgrade   = maxGradeEl ? (parseFloat(maxGradeEl.value) || 0) : 0;
                var scoreEls   = document.querySelectorAll('#airagassign-rubric-body .airag-score-input');
                var total      = 0;
                scoreEls.forEach(function(el) { total += parseFloat(el.value) || 0; });
                var isValid = maxgrade > 0 && Math.abs(total - maxgrade) <= 0.01;
                var summary = document.getElementById('airagassign-rubric-summary');

                // Apply Bootstrap is-invalid / is-valid classes per individual score input:
                // - no maxgrade set yet  → no feedback
                // - value <= 0 or empty  → always is-invalid (must be filled > 0)
                // - value > 0 but sum ≠ max → is-invalid (sum mismatch)
                // - value > 0 and sum == max → is-valid
                scoreEls.forEach(function(el) {
                    var val = parseFloat(el.value);
                    var hasValue = !isNaN(val) && val > 0;
                    if (maxgrade <= 0) {
                        el.classList.remove('is-invalid', 'is-valid');
                    } else if (!hasValue) {
                        el.classList.remove('is-valid');
                        el.classList.add('is-invalid');
                    } else if (isValid) {
                        el.classList.remove('is-invalid');
                        el.classList.add('is-valid');
                    } else {
                        el.classList.remove('is-valid');
                        el.classList.add('is-invalid');
                    }
                });

                if (!summary) return;
                if (maxgrade <= 0) { summary.innerHTML = ''; return; }

                var t = parseFloat(total.toFixed(2));
                var m = parseFloat(maxgrade.toFixed(2));
                if (isValid) {
                    summary.innerHTML =
                        '<div class="alert alert-success py-2 px-3 mb-0 d-flex align-items-center gap-2">'
                        + '<strong>' + t + ' / ' + m + '</strong>'
                        + '<span>&mdash; ' + lblMatch + '</span></div>';
                } else {
                    var diff = total - maxgrade;
                    var sign = diff > 0 ? '+' : '';
                    summary.innerHTML =
                        '<div class="alert alert-danger py-2 px-3 mb-0 d-flex align-items-center gap-2">'
                        + '<strong>' + t + ' / ' + m + '</strong>'
                        + '<span>(' + lblDiff + ': ' + sign + parseFloat(diff.toFixed(2)) + ')'
                        + ' &mdash; ' + lblErr + '</span></div>';
                }
            }

            // ── Build new row ────────────────────────────────────────────────────
            function makeRow(i) {
                var tr = document.createElement('tr');
                tr.className = 'airag-rubric-row';
                var td1 = '<td><input type="text" name="criterionname[' + i + ']"'
                        + ' placeholder="' + nameph.replace(/"/g, '&quot;') + '" class="form-control form-control-sm"></td>';
                var td2 = '<td><input type="text" name="criteriondesc[' + i + ']"'
                        + ' placeholder="' + descph.replace(/"/g, '&quot;') + '" class="form-control form-control-sm"></td>';
                var td3 = '<td><input type="number" name="criterionmaxscore[' + i + ']"'
                        + ' placeholder="e.g. 40" min="0" step="any"'
                        + ' class="form-control form-control-sm airag-score-input"></td>';
                var td4 = '<td class="text-center align-middle">'
                        + '<button type="button" class="btn btn-sm btn-outline-danger airag-del-criterion"'
                        + ' title="' + dellbl + '">&#x2715; ' + dellbl + '</button></td>';
                tr.innerHTML = td1 + td2 + td3 + td4;
                return tr;
            }

            // ── Initialise everything ────────────────────────────────────────────
            function init() {
                var tbody = document.getElementById('airagassign-rubric-body');
                var frm   = tbody && tbody.closest('form');

                // Initial score check
                updateRubricSummary();

                // Watch score inputs (event delegation — covers dynamic rows)
                tbody.addEventListener('input', function(e) {
                    if (e.target.classList.contains('airag-score-input')) {
                        updateRubricSummary();
                    }
                });

                // Watch maximumgrade field changes — document delegation is Moodle-safe:
                // guarantees the listener fires even if the element is found late or
                // its name/id differs between Moodle versions.
                document.addEventListener('input', function(e) {
                    if (e.target && (
                        (e.target.name && e.target.name.indexOf('grade[') === 0) ||
                        (e.target.id && e.target.id.indexOf('id_grade_') === 0)
                    )) { updateRubricSummary(); }
                });
                document.addEventListener('change', function(e) {
                    if (e.target && (
                        (e.target.name && e.target.name.indexOf('grade[') === 0) ||
                        (e.target.id && e.target.id.indexOf('id_grade_') === 0)
                    )) { updateRubricSummary(); }
                });
                // Delayed fallback: re-run initial check after Moodle JS finishes setup
                setTimeout(updateRubricSummary, 300);

                // Add row
                document.getElementById('airagassign-add-criterion').addEventListener('click', function() {
                    tbody.appendChild(makeRow(idx++));
                    updateRubricSummary();
                });

                // Delete row (delegated)
                tbody.addEventListener('click', function(e) {
                    var btn = e.target.closest('.airag-del-criterion');
                    if (!btn) return;
                    if (tbody.querySelectorAll('tr.airag-rubric-row').length <= 1) {
                        alert(alertmin);
                        return;
                    }
                    btn.closest('tr').remove();
                    updateRubricSummary();
                });

                // Serialize + refresh visual state on submit
                if (frm) {
                    frm.addEventListener('submit', function() {
                        updateRubricSummary();
                        var rows = document.querySelectorAll('#airagassign-rubric-body tr.airag-rubric-row');
                        var arr  = [];
                        rows.forEach(function(row) {
                            arr.push({
                                name:     (row.querySelector('input[name^="criterionname"]')     || {value: ''}).value,
                                desc:     (row.querySelector('input[name^="criteriondesc"]')     || {value: ''}).value,
                                maxscore: (row.querySelector('.airag-score-input')               || {value: ''}).value
                            });
                        });
                        var hid = frm.querySelector('input[name="criteria_json"]');
                        if (hid) hid.value = JSON.stringify(arr);
                    });
                }

                // Force expand grade section if collapsed (client-side override).
                setTimeout(function() {
                    var gradeHeader = document.getElementById('id_modstandardgrade');
                    if (gradeHeader) {
                        var isCollapsed = gradeHeader.classList.contains('collapsed') || 
                                          gradeHeader.getAttribute('aria-expanded') === 'false';
                        if (isCollapsed) {
                            var toggler = gradeHeader.querySelector('.ftoggler a, [data-toggle="collapse"], .fheader, legend a');
                            if (toggler) {
                                toggler.click();
                            } else {
                                gradeHeader.classList.remove('collapsed');
                                var collapseEl = gradeHeader.querySelector('.collapse');
                                if (collapseEl) {
                                    collapseEl.classList.add('show');
                                }
                            }
                        }
                    }
                }, 500);

                // Force remove Marking guide option from advancedgradingmethod_submissions dropdown.
                // Moodle's internal value is usually "guide"; older/local code
                // may refer to it as "markingguide", so remove both.
                var gradingSelect = document.querySelector('select[name="advancedgradingmethod_submissions"]');
                if (gradingSelect) {
                    var unsupportedMethods = ['guide', 'markingguide'];
                    for (var i = gradingSelect.options.length - 1; i >= 0; i--) {
                        if (unsupportedMethods.indexOf(gradingSelect.options[i].value) !== -1) {
                            gradingSelect.remove(i);
                        }
                    }

                    var order = ['custom', '', 'rubric'];
                    order.forEach(function(value) {
                        var option = Array.prototype.find.call(gradingSelect.options, function(opt) {
                            return opt.value === value;
                        });
                        if (option) {
                            gradingSelect.appendChild(option);
                        }
                    });
                }
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', init);
            } else {
                init();
            }
        })();
        </script>
        HTML;
    }

    /**
     * Build interactive numbered questions list with add/delete functionality.
     * Uses plain <textarea> with names questions[i] — identical to what lib.php reads.
     *
     * NOTE: Uses PHP heredoc so single quotes in JS are never escaped.
     *
     * @param array $questions Array of question text strings (indexed)
     * @return string HTML
     */
    private function _build_questions_list(array $questions): string {
        $ph      = s(get_string('question_placeholder', 'airagassign'));
        $addlbl  = s(get_string('addquestion', 'airagassign'));
        $dellbl_s = s(get_string('delete', 'core'));
        $hint    = s(get_string('questions_required_hint', 'airagassign'));

        // JS values via json_encode (produces safe double-quoted JS strings).
        $js_ph       = json_encode(get_string('question_placeholder', 'airagassign'));
        $js_dellbl   = json_encode(get_string('delete', 'core'));
        $js_alertmin = json_encode(get_string('questions_required_error', 'airagassign'));

        $rowshtml = '';
        $nextidx  = 0;
        foreach ($questions as $i => $qtext) {
            $val = s((string)$qtext);
            $num = $i + 1;
            $rowshtml .= <<<HTML
            <div class="airag-question-row d-flex align-items-start mb-3 gap-2">
                <span class="fw-bold pt-2" style="min-width:28px">{$num}.</span>
                <div style="flex:1">
                    <textarea name="questions[{$i}]" rows="3"
                        class="form-control airag-question-ta" placeholder="{$ph}">{$val}</textarea>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger mt-1 airag-del-question"
                    title="{$dellbl_s}">&#x2715;</button>
            </div>
            HTML;
            $nextidx = $i + 1;
        }

        return <<<HTML
        <div class="alert alert-info py-2 mb-3">{$hint}</div>
        <div id="airagassign-questions-wrap">{$rowshtml}</div>
        <div id="airagassign-questions-summary" class="mt-2 mb-2"></div>
        <button type="button" class="btn btn-sm btn-outline-primary mt-1" id="airagassign-add-question">
            + {$addlbl}
        </button>
        <script>
        (function() {
            var idx      = {$nextidx};
            var ph       = {$js_ph};
            var dellbl   = {$js_dellbl};
            var alertmin = {$js_alertmin};
            var touched  = false; // only show feedback after first interaction

            // ── Real-time questions feedback ─────────────────────────────────────
            function updateQuestionsSummary(force) {
                var summary = document.getElementById('airagassign-questions-summary');
                if (!summary) return;
                if (!force && !touched) { summary.innerHTML = ''; return; }

                var tas    = document.querySelectorAll('#airagassign-questions-wrap .airag-question-ta');
                var filled = 0;
                tas.forEach(function(ta) { if (ta.value.trim().length > 0) filled++; });
                var total = tas.length;

                // Apply is-invalid only on submit (force=true) to avoid aggressive early styling
                if (force) {
                    tas.forEach(function(ta) {
                        if (ta.value.trim().length === 0 && filled === 0) {
                            ta.classList.add('is-invalid');
                            ta.classList.remove('is-valid');
                        } else if (ta.value.trim().length > 0) {
                            ta.classList.remove('is-invalid');
                            ta.classList.add('is-valid');
                        } else {
                            ta.classList.remove('is-invalid', 'is-valid');
                        }
                    });
                }

                if (filled === 0) {
                    summary.innerHTML =
                        '<div class="alert alert-danger py-2 px-3 mb-0">'
                        + '&#x2716; ' + alertmin + '</div>';
                } else {
                    summary.innerHTML =
                        '<div class="alert alert-success py-2 px-3 mb-0">'
                        + '&#x2714; ' + filled + ' / ' + total + ' pertanyaan telah diisi</div>';
                }
            }

            function renumber() {
                var rows = document.querySelectorAll('#airagassign-questions-wrap .airag-question-row');
                rows.forEach(function(row, n) {
                    var el = row.querySelector('span.fw-bold');
                    if (el) el.textContent = (n + 1) + '.';
                });
            }

            function init() {
                var wrap = document.getElementById('airagassign-questions-wrap');
                var frm  = wrap && wrap.closest('form');

                // Add question
                document.getElementById('airagassign-add-question').addEventListener('click', function() {
                    var num = wrap.querySelectorAll('.airag-question-row').length + 1;
                    var div = document.createElement('div');
                    div.className = 'airag-question-row d-flex align-items-start mb-3 gap-2';
                    div.innerHTML =
                        '<span class="fw-bold pt-2" style="min-width:28px">' + num + '.</span>'
                        + '<div style="flex:1">'
                        + '<textarea name="questions[' + idx + ']" rows="3"'
                        + ' class="form-control airag-question-ta"'
                        + ' placeholder="' + ph.replace(/"/g, '&quot;') + '"></textarea></div>'
                        + '<button type="button"'
                        + ' class="btn btn-sm btn-outline-danger mt-1 airag-del-question"'
                        + ' title="' + dellbl + '">&#x2715;</button>';
                    wrap.appendChild(div);
                    idx++;
                    updateQuestionsSummary();
                });

                // Delete question (delegated)
                wrap.addEventListener('click', function(e) {
                    var btn = e.target.closest('.airag-del-question');
                    if (!btn) return;
                    if (wrap.querySelectorAll('.airag-question-row').length <= 1) {
                        alert(alertmin);
                        return;
                    }
                    btn.closest('.airag-question-row').remove();
                    renumber();
                    updateQuestionsSummary();
                });

                // Live feedback on typing
                wrap.addEventListener('input', function(e) {
                    if (e.target.classList.contains('airag-question-ta')) {
                        touched = true;
                        updateQuestionsSummary();
                    }
                });

                // Serialize + refresh visual on submit
                if (frm) {
                    frm.addEventListener('submit', function() {
                        touched = true;
                        updateQuestionsSummary(true);
                        var tas = document.querySelectorAll('#airagassign-questions-wrap .airag-question-ta');
                        var arr = [];
                        tas.forEach(function(ta) { arr.push(ta.value); });
                        var hid = frm.querySelector('input[name="questions_json"]');
                        if (hid) hid.value = JSON.stringify(arr);
                    });
                }
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', init);
            } else {
                init();
            }
        })();
        </script>
        HTML;
    }

    /**
     * Remove a select option without MoodleQuickForm_select::removeOption().
     *
     * Moodle's removeOption() assumes the select values are already an array.
     * On the add-activity form that value can still be null, which causes a
     * TypeError in PHP 8. This helper removes options defensively and only
     * cleans selected values when they have been initialized.
     *
     * @param HTML_QuickForm_select $select The select element.
     * @param string $value Option value to remove.
     * @return void
     */
    private function remove_select_option_safely($select, string $value): void {
        if (isset($select->_options) && is_array($select->_options)) {
            foreach ($select->_options as $key => $option) {
                $optionvalue = $option['attr']['value'] ?? null;
                if ((string)$optionvalue === $value) {
                    unset($select->_options[$key]);
                }
            }
            $select->_options = array_values($select->_options);
        }

        if (isset($select->_values) && is_array($select->_values)) {
            $select->_values = array_values(array_filter($select->_values, function($selected) use ($value) {
                return (string)$selected !== $value;
            }));
        }
    }

    /**
     * Order grading method options as requested by the UI flow.
     *
     * The option values remain unchanged:
     * - custom: plugin built-in custom rubric
     * - empty string: Moodle simple direct grading
     * - rubric: Moodle native rubric
     *
     * @param HTML_QuickForm_select $select The grading method select element.
     * @return void
     */
    private function order_grading_method_options($select): void {
        if (!isset($select->_options) || !is_array($select->_options)) {
            return;
        }

        $order = ['custom', '', 'rubric'];
        $ordered = [];
        $remaining = [];

        foreach ($select->_options as $option) {
            $optionvalue = (string)($option['attr']['value'] ?? '');
            $position = array_search($optionvalue, $order, true);
            if ($position === false) {
                $remaining[] = $option;
            } else {
                $ordered[$position] = $option;
            }
        }

        ksort($ordered);
        $select->_options = array_values(array_merge($ordered, $remaining));
    }

    public function validation($data, $files) {
        global $USER;
        $errors = parent::validation($data, $files);

        // 1a. At least one of select materials or manual file must be provided.
        $hasmaterials = !empty($data['materials']);
        $hasmanualfile = false;
        $draftitemid = !empty($data['manualfile']) ? (int)$data['manualfile'] : 0;
        if ($draftitemid) {
            $fs = get_file_storage();
            $usercontext = \context_user::instance($USER->id);
            $draftfiles = $fs->get_area_files($usercontext->id, 'user', 'draft', $draftitemid, 'id DESC', false);
            if (!empty($draftfiles)) {
                $hasmanualfile = true;
            }
        }
        if (!$hasmaterials && !$hasmanualfile) {
            $msg = 'At least one of "Select course materials" or "Manual Reference / Answer Key File" must be provided.';
            if (current_language() === 'id') {
                $msg = 'Setidaknya salah satu dari "Pilih materi pembelajaran" atau "Berkas Acuan / Kunci Jawaban (Manual)" harus diisi.';
            }
            if (get_string_manager()->string_exists('knowledgebase_required_error', 'mod_airagassign')) {
                $msg = get_string('knowledgebase_required_error', 'mod_airagassign');
            } else if (get_string_manager()->string_exists('knowledgebase_required_error', 'airagassign')) {
                $msg = get_string('knowledgebase_required_error', 'airagassign');
            }
            $errors['manualfile'] = $msg;
            $errors['materials'] = $msg;
        }

        // 1b. Open date must be before due date when both are set.
        $opendate = intval($data['opendate'] ?? 0);
        $duedate  = intval($data['duedate']  ?? 0);
        if ($opendate > 0 && $duedate > 0 && $opendate >= $duedate) {
            $errors['opendate'] = get_string('opendate_before_duedate_error', 'airagassign');
        }

        // 2. Essay mode: essay prompt is required.
        if ($data['assignmode'] === 'essay') {
            if (empty(trim($data['essayprompt'] ?? ''))) {
                $errors['essayprompt'] = get_string('essayprompt_required', 'airagassign');
            }
        }

        // 3. Quiz mode: decode questions_json (registered hidden field).
        if ($data['assignmode'] === 'quiz') {
            // Override the check above using the JSON field.
            $questionsarr = json_decode($data['questions_json'] ?? '[]', true);
            if (!is_array($questionsarr)) {
                $questionsarr = [];
            }
            $hasquestion = false;
            foreach ($questionsarr as $q) {
                if (!empty(trim((string)$q))) {
                    $hasquestion = true;
                    break;
                }
            }
            if (!$hasquestion) {
                $errors['questions_json'] = get_string('questions_required_error', 'airagassign');
            }
        }

        // 4. At least one non-empty rubric criterion, and calculate total score.
        if (isset($data['advancedgradingmethod_submissions']) && $data['advancedgradingmethod_submissions'] === 'custom') {
            $hascriterion = false;
            $criterionsum = 0.0;
            $criteriaarr  = json_decode($data['criteria_json'] ?? '[]', true);
            if (!is_array($criteriaarr)) {
                $criteriaarr = [];
            }
            foreach ($criteriaarr as $c) {
                if (!empty(trim((string)($c['name'] ?? '')))) {
                    $hascriterion  = true;
                    $criterionsum += floatval($c['maxscore'] ?? 0);
                }
            }
            if (!$hascriterion) {
                $errors['criteria_json'] = get_string('criterion_required_error', 'airagassign');
            }

            // 5. Rubric sum must equal maximum grade (tolerance 0.01 for float rounding).
            $maxgrade = 0.0;
            if (isset($data['grade'])) {
                if (is_array($data['grade'])) {
                    if (isset($data['grade']['modgrade_type']) && $data['grade']['modgrade_type'] === 'point') {
                        $maxgrade = floatval($data['grade']['modgrade_point'] ?? 0);
                    }
                } else if (is_numeric($data['grade'])) {
                    $maxgrade = floatval($data['grade']);
                }
            }

            if ($hascriterion && $maxgrade >= 1) {
                if (abs($criterionsum - $maxgrade) > 0.01) {
                    $a      = new stdClass();
                    $a->sum = number_format($criterionsum, 2);
                    $a->max = number_format($maxgrade, 2);
                    $errors['criteria_json'] = get_string('rubric_score_mismatch', 'airagassign', $a);
                }
            }
        }

        return $errors;
    }
}
