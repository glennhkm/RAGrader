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
 * Custom rubric editor for RAG AI grading.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

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
require_once($CFG->dirroot . '/mod/assign/locallib.php');
require_once($CFG->dirroot . '/local/assign_ai_rag/locallib.php');

$cmid = required_param('id', PARAM_INT);
$action = optional_param('action', '', PARAM_ALPHA);

// Get the course module and the course.
$cm = get_coursemodule_from_id('assign', $cmid, 0, false, MUST_EXIST);
$course = $DB->get_record('course', ['id' => $cm->course], '*', MUST_EXIST);
$context = context_module::instance($cm->id);

require_login($course, true, $cm);
require_capability('local/assign_ai_rag:review', $context);

// Instantiate the assign object.
$assign = new assign($context, $cm, $course);
$assignment = $assign->get_instance();

// Get existing rubric.
$existingrubric = $DB->get_record('local_assign_ai_rag_rubric', ['assignmentid' => $cmid]);

// Handle form submission.
if ($action === 'save') {
    require_sesskey();
    
    $rubricjson = required_param('rubric_json', PARAM_RAW);
    $maxgrade = required_param('max_grade', PARAM_INT);
    
    // Validate JSON.
    $rubricdata = json_decode($rubricjson, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        \core\notification::error(get_string('invalidjson', 'local_assign_ai_rag'));
        redirect(new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid]));
    }
    
    // Validate rubric structure.
    if (!isset($rubricdata['criteria']) || !is_array($rubricdata['criteria'])) {
        \core\notification::error(get_string('invalidrubricstructure', 'local_assign_ai_rag'));
        redirect(new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid]));
    }
    
    $now = time();
    
    if ($existingrubric) {
        // Update existing.
        $existingrubric->rubric_json = $rubricjson;
        $existingrubric->max_grade = $maxgrade;
        $existingrubric->usermodified = $USER->id;
        $existingrubric->timemodified = $now;
        $DB->update_record('local_assign_ai_rag_rubric', $existingrubric);
    } else {
        // Insert new.
        $record = (object)[
            'assignmentid' => $cmid,
            'rubric_json' => $rubricjson,
            'max_grade' => $maxgrade,
            'usermodified' => $USER->id,
            'timecreated' => $now,
            'timemodified' => $now,
        ];
        $DB->insert_record('local_assign_ai_rag_rubric', $record);
    }
    
    \core\notification::success(get_string('rubricsaved', 'local_assign_ai_rag'));
    redirect(new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid]));
}

// Handle delete action.
if ($action === 'delete' && $existingrubric) {
    require_sesskey();
    $DB->delete_records('local_assign_ai_rag_rubric', ['id' => $existingrubric->id]);
    \core\notification::success(get_string('rubricdeleted', 'local_assign_ai_rag'));
    redirect(new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid]));
}

// Page setup.
$PAGE->set_url(new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid]));
$PAGE->set_course($course);
$PAGE->set_context($context);
$PAGE->set_title(get_string('rubriceditor', 'local_assign_ai_rag'));
$PAGE->set_heading(format_string($course->fullname));
$PAGE->activityheader->disable();

// Default rubric template.
$defaultrubric = [
    'criteria' => [
        'Pemahaman Konsep' => [
            'points' => 25,
            'description' => 'Kemampuan memahami dan menjelaskan konsep utama',
            'levels' => [
                'excellent' => 'Memahami konsep dengan sangat baik dan dapat menjelaskan dengan contoh yang tepat',
                'good' => 'Memahami konsep dengan baik',
                'fair' => 'Pemahaman konsep cukup namun masih ada kesalahan minor',
                'poor' => 'Pemahaman konsep kurang atau banyak kesalahan'
            ]
        ],
        'Analisis' => [
            'points' => 25,
            'description' => 'Kemampuan menganalisis dan menghubungkan konsep',
            'levels' => [
                'excellent' => 'Analisis mendalam dan komprehensif',
                'good' => 'Analisis baik dengan penjelasan yang jelas',
                'fair' => 'Analisis cukup namun kurang mendalam',
                'poor' => 'Analisis kurang atau tidak ada'
            ]
        ],
        'Kelengkapan Jawaban' => [
            'points' => 25,
            'description' => 'Kelengkapan dan kedalaman jawaban',
            'levels' => [
                'excellent' => 'Jawaban sangat lengkap dan mencakup semua aspek yang diminta',
                'good' => 'Jawaban lengkap',
                'fair' => 'Jawaban cukup lengkap namun ada yang terlewat',
                'poor' => 'Jawaban tidak lengkap'
            ]
        ],
        'Referensi dan Sitasi' => [
            'points' => 25,
            'description' => 'Penggunaan referensi dari materi kuliah',
            'levels' => [
                'excellent' => 'Menggunakan banyak referensi yang relevan dari materi kuliah',
                'good' => 'Menggunakan beberapa referensi yang relevan',
                'fair' => 'Menggunakan sedikit referensi',
                'poor' => 'Tidak ada referensi atau referensi tidak relevan'
            ]
        ]
    ]
];

$currentrubric = $existingrubric ? json_decode($existingrubric->rubric_json, true) : $defaultrubric;
$maxgrade = $existingrubric ? $existingrubric->max_grade : (int)$assignment->grade;

echo $OUTPUT->header();

// Back button.
$backurl = new moodle_url('/local/assign_ai_rag/review.php', ['id' => $cmid]);
echo '<div class="mb-3">';
echo '<a href="' . $backurl->out(false) . '" class="btn btn-secondary">&larr; ' . get_string('backtoreview', 'local_assign_ai_rag') . '</a>';
echo '</div>';

// Title.
echo '<h2>' . get_string('rubriceditor', 'local_assign_ai_rag') . '</h2>';
echo '<p class="text-muted">' . get_string('assignment', 'local_assign_ai_rag') . ': ' . s($assignment->name) . '</p>';

// Info box.
echo '<div class="alert alert-info">';
echo '<strong>' . get_string('rubricinfo', 'local_assign_ai_rag') . '</strong><br>';
echo get_string('rubricinfodesc', 'local_assign_ai_rag');
echo '</div>';

// Form.
$saveurl = new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid, 'action' => 'save', 'sesskey' => sesskey()]);
echo '<form method="post" action="' . $saveurl->out(false) . '" id="rubricForm">';

// Max grade.
echo '<div class="mb-3">';
echo '<label for="max_grade" class="form-label"><strong>' . get_string('maxgrade', 'local_assign_ai_rag') . '</strong></label>';
echo '<input type="number" class="form-control" id="max_grade" name="max_grade" value="' . $maxgrade . '" min="1" max="1000" style="max-width: 150px;">';
echo '<small class="text-muted">' . get_string('maxgradehint', 'local_assign_ai_rag') . '</small>';
echo '</div>';

// Visual rubric editor.
echo '<div class="card mb-4">';
echo '<div class="card-header">';
echo '<strong>' . get_string('rubriccriteria', 'local_assign_ai_rag') . '</strong>';
echo '<button type="button" class="btn btn-sm btn-primary float-end" onclick="addCriterion()">+ ' . get_string('addcriterion', 'local_assign_ai_rag') . '</button>';
echo '</div>';
echo '<div class="card-body" id="criteriaContainer">';
// Criteria will be populated by JavaScript.
echo '</div>';
echo '</div>';

// JSON preview/editor.
echo '<div class="mb-3">';
echo '<label for="rubric_json" class="form-label"><strong>' . get_string('rubricjson', 'local_assign_ai_rag') . '</strong></label>';
echo '<textarea class="form-control font-monospace" id="rubric_json" name="rubric_json" rows="15">';
echo s(json_encode($currentrubric, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
echo '</textarea>';
echo '<small class="text-muted">' . get_string('rubricjsonhint', 'local_assign_ai_rag') . '</small>';
echo '</div>';

// Buttons.
echo '<div class="mb-4">';
echo '<button type="submit" class="btn btn-primary btn-lg me-2">💾 ' . get_string('saverubric', 'local_assign_ai_rag') . '</button>';
echo '<button type="button" class="btn btn-outline-secondary" onclick="resetToDefault()">🔄 ' . get_string('resettodefault', 'local_assign_ai_rag') . '</button>';
if ($existingrubric) {
    $deleteurl = new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid, 'action' => 'delete', 'sesskey' => sesskey()]);
    echo ' <a href="' . $deleteurl->out(false) . '" class="btn btn-outline-danger" onclick="return confirm(\'' . get_string('confirmdelete', 'local_assign_ai_rag') . '\')">🗑 ' . get_string('deleterubric', 'local_assign_ai_rag') . '</a>';
}
echo '</div>';

echo '</form>';

// Example format.
echo '<div class="card mb-4">';
echo '<div class="card-header"><strong>' . get_string('exampleformat', 'local_assign_ai_rag') . '</strong></div>';
echo '<div class="card-body">';
echo '<pre class="bg-light p-3"><code>';
$example = [
    'criteria' => [
        'Criterion Name' => [
            'points' => 25,
            'description' => 'Description of this criterion',
            'levels' => [
                'excellent' => 'Full marks description',
                'good' => 'Good performance description',
                'fair' => 'Fair performance description',
                'poor' => 'Poor performance description'
            ]
        ]
    ]
];
echo s(json_encode($example, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
echo '</code></pre>';
echo '</div>';
echo '</div>';

// JavaScript for visual editor.
?>
<script>
const defaultRubric = <?php echo json_encode($defaultrubric); ?>;
let currentRubric = <?php echo json_encode($currentrubric); ?>;

function renderCriteria() {
    const container = document.getElementById('criteriaContainer');
    container.innerHTML = '';
    
    const criteria = currentRubric.criteria || {};
    let index = 0;
    
    for (const [name, data] of Object.entries(criteria)) {
        const card = document.createElement('div');
        card.className = 'card mb-3';
        card.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                <input type="text" class="form-control form-control-sm me-2" value="${escapeHtml(name)}" 
                       onchange="updateCriterionName(${index}, '${escapeHtml(name)}', this.value)" 
                       placeholder="Criterion name" style="max-width: 300px;">
                <div>
                    <input type="number" class="form-control form-control-sm d-inline-block" value="${data.points || 0}" 
                           onchange="updateCriterionPoints(${index}, '${escapeHtml(name)}', this.value)" 
                           style="width: 80px;" min="0"> points
                    <button type="button" class="btn btn-sm btn-danger ms-2" onclick="removeCriterion('${escapeHtml(name)}')">&times;</button>
                </div>
            </div>
            <div class="card-body">
                <div class="mb-2">
                    <label class="form-label">Description:</label>
                    <input type="text" class="form-control form-control-sm" value="${escapeHtml(data.description || '')}"
                           onchange="updateCriterionDesc('${escapeHtml(name)}', this.value)">
                </div>
                <div class="mb-2">
                    <label class="form-label">Levels:</label>
                    ${renderLevels(name, data.levels || {})}
                </div>
            </div>
        `;
        container.appendChild(card);
        index++;
    }
    
    updateJsonTextarea();
}

function renderLevels(criterionName, levels) {
    const levelNames = ['excellent', 'good', 'fair', 'poor'];
    let html = '<div class="row">';
    
    for (const level of levelNames) {
        html += `
            <div class="col-md-3 mb-2">
                <label class="form-label text-capitalize">${level}:</label>
                <textarea class="form-control form-control-sm" rows="2" 
                          onchange="updateLevel('${escapeHtml(criterionName)}', '${level}', this.value)">${escapeHtml(levels[level] || '')}</textarea>
            </div>
        `;
    }
    
    html += '</div>';
    return html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function addCriterion() {
    const name = prompt('Enter criterion name:', 'New Criterion');
    if (name) {
        currentRubric.criteria = currentRubric.criteria || {};
        currentRubric.criteria[name] = {
            points: 25,
            description: '',
            levels: {
                excellent: '',
                good: '',
                fair: '',
                poor: ''
            }
        };
        renderCriteria();
    }
}

function removeCriterion(name) {
    if (confirm('Remove criterion "' + name + '"?')) {
        delete currentRubric.criteria[name];
        renderCriteria();
    }
}

function updateCriterionName(index, oldName, newName) {
    if (oldName !== newName && newName) {
        const data = currentRubric.criteria[oldName];
        delete currentRubric.criteria[oldName];
        currentRubric.criteria[newName] = data;
        renderCriteria();
    }
}

function updateCriterionPoints(index, name, points) {
    currentRubric.criteria[name].points = parseInt(points) || 0;
    updateJsonTextarea();
}

function updateCriterionDesc(name, desc) {
    currentRubric.criteria[name].description = desc;
    updateJsonTextarea();
}

function updateLevel(criterionName, level, value) {
    currentRubric.criteria[criterionName].levels[level] = value;
    updateJsonTextarea();
}

function updateJsonTextarea() {
    document.getElementById('rubric_json').value = JSON.stringify(currentRubric, null, 2);
}

function resetToDefault() {
    if (confirm('Reset rubric to default template?')) {
        currentRubric = JSON.parse(JSON.stringify(defaultRubric));
        renderCriteria();
    }
}

// Sync JSON textarea changes to visual editor.
document.getElementById('rubric_json').addEventListener('change', function() {
    try {
        currentRubric = JSON.parse(this.value);
        renderCriteria();
    } catch (e) {
        alert('Invalid JSON: ' + e.message);
    }
});

// Initial render.
document.addEventListener('DOMContentLoaded', function() {
    renderCriteria();
});
</script>
<?php

echo $OUTPUT->footer();
