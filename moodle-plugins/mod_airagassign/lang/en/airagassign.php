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
 * Language strings for AI RAG Assignment module.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

// General.
$string['modulename'] = 'AI RAG Assignment';
$string['modulenameplural'] = 'AI RAG Assignments';
$string['modulename_help'] = 'The AI RAG Assignment module allows teachers to create assignments that are automatically graded using AI with Retrieval-Augmented Generation (RAG). It supports two modes: Quiz mode (multiple short-answer questions) and Essay mode (single essay response). The AI uses previously uploaded course materials as its knowledge base for grading.';
$string['pluginname'] = 'AI RAG Assignment';
$string['pluginadministration'] = 'AI RAG Assignment administration';
$string['airagassign:addinstance'] = 'Add a new AI RAG Assignment';
$string['airagassign:view'] = 'View AI RAG Assignment';
$string['airagassign:submit'] = 'Submit answers to AI RAG Assignment';
$string['airagassign:grade'] = 'Grade AI RAG Assignment submissions';
$string['airagassign:manage'] = 'Manage AI RAG Assignment';
$string['airagassign:viewallsubmissions'] = 'View all student submissions';

// Form fields.
$string['assignmentname'] = 'Assignment name';
$string['assignmentname_help'] = 'Enter a descriptive name for this AI RAG assignment.';
$string['assignmentmode'] = 'Assignment mode';
$string['assignmentmode_help'] = 'Choose the type of assignment: Quiz mode presents multiple short-answer questions, while Essay mode requires a single essay response.';
$string['mode_quiz'] = 'Quiz (Short Answer)';
$string['mode_essay'] = 'Essay';
$string['maximumgrade'] = 'Maximum grade';
$string['maximumgrade_help'] = 'The maximum grade achievable for this assignment. Minimum value is 1. The total of all rubric criterion scores must equal this value exactly.';
$string['duedate'] = 'Due date';
$string['duedate_help'] = 'After this date, students can no longer submit and the teacher can grade with AI.';
$string['opendate'] = 'Open date';
$string['opendate_help'] = 'Students cannot submit before this date. Leave disabled to allow submissions immediately after the activity is created.';
$string['opendate_before_duedate_error'] = 'The open date must be earlier than the due date.';
$string['dateorder_hint'] = 'Warning: the open date must be earlier than the due date.';
$string['notavailableyet'] = 'This assignment is not yet available. It will open on {$a}.';
$string['opened'] = 'Open';
$string['allowlatesubmission'] = 'Allow late submissions';

// Materials selection.
$string['materialsheader'] = 'RAG Knowledge Base';
$string['selectmaterials'] = 'Select course materials';
$string['selectmaterials_help'] = 'Select one or more AI RAG Material activities from this course. The uploaded materials will be used as the AI knowledge base for grading.';
$string['nomaterials'] = 'No AI RAG Material activities found in this course. Please add and vectorize materials first.';
$string['nomaterialsavailable'] = 'This assignment cannot accept submissions right now because no linked materials have been vectorized yet. Please contact your teacher.';
$string['selectedmaterials'] = 'Selected materials for RAG context';

// Rubric.
$string['rubricheader'] = 'Grading rubric';
$string['rubriccriteria'] = 'Rubric criteria';
$string['rubriccriteria_help'] = 'Define the grading criteria. Each criterion has a name, description, and maximum score. The AI will evaluate submissions against each criterion.';
$string['criterionname'] = 'Criterion name';
$string['criteriondesc'] = 'Description';
$string['criterionmaxscore'] = 'Max score';
$string['addcriterion'] = 'Add criterion';
$string['removecriterion'] = 'Remove';
$string['defaultcriterion_relevance'] = 'Relevance';
$string['defaultcriterion_relevance_desc'] = 'How well the answer addresses the question using relevant course material.';
$string['defaultcriterion_accuracy'] = 'Accuracy';
$string['defaultcriterion_accuracy_desc'] = 'Correctness of facts and concepts based on course materials.';
$string['defaultcriterion_completeness'] = 'Completeness';
$string['defaultcriterion_completeness_desc'] = 'Thoroughness and coverage of key points from the material.';

// Quiz mode questions.
$string['questionsheader'] = 'Questions';
$string['questions_help'] = 'Add questions for the quiz. Each question will be graded individually using the rubric criteria.';
$string['questiontext'] = 'Question {$a}';
$string['addquestion'] = 'Add question';
$string['removequestion'] = 'Remove question';
$string['numquestions'] = 'Number of questions: {$a}';

// Essay mode.
$string['essayprompt'] = 'Essay prompt';
$string['essayprompt_help'] = 'Describe the essay assignment. This is the question/prompt that students will respond to.';
$string['minwords'] = 'Minimum word count';
$string['maxwords'] = 'Maximum word count';

// Submission.
$string['youranswer'] = 'Your answer';
$string['youressay'] = 'Your essay';
$string['submitanswers'] = 'Submit answers';
$string['submitessay'] = 'Submit essay';
$string['confirmsubmit'] = 'Are you sure you want to submit? You cannot change your answers after submission.';
$string['submissionsaved'] = 'Your submission has been saved.';
$string['alreadysubmitted'] = 'You have already submitted this assignment.';
$string['notallowedsinceclosed'] = 'This assignment is closed. Submissions are no longer accepted.';
$string['wordcount'] = 'Word count: {$a}';
$string['wordcountbelowmin'] = 'Your essay must be at least {$a} words.';
$string['wordcountabovemax'] = 'Your essay must not exceed {$a} words.';

// Grading.
$string['gradewithairag'] = 'Grade with AI RAG';
$string['gradingall'] = 'Grade all submissions with AI RAG';
$string['gradesubmission'] = 'Grade this submission';
$string['grading'] = 'Grading...';
$string['status_grading_failed'] = 'AI grading failed';
$string['retrygrading'] = 'Retry AI grading';
$string['grading_requestid'] = 'Request ID';
$string['graded'] = 'Graded';
$string['notgraded'] = 'Not graded';
$string['gradingsuccess'] = 'Successfully graded submission for {$a}.';
$string['gradingerror'] = 'Error grading submission for {$a->student}: {$a->error}';
$string['gradingcomplete'] = 'AI grading complete. {$a->success} of {$a->total} submissions graded successfully.';
$string['moodlerubric_not_configured'] = 'Moodle Native Rubric is selected, but no active rubric criteria are configured yet. Save the assignment, open Advanced grading, define the rubric, then run AI grading again.';
$string['nogradablesubmissions'] = 'No submissions to grade. Either no students have submitted, or the due date has not passed yet.';
$string['overrideduedate'] = 'Due date has not passed yet. Grade anyway?';
$string['viewresult'] = 'View result';
$string['resultsfor'] = 'AI Grading Results for {$a}';
$string['overallscore'] = 'Overall score';
$string['overallfeedback'] = 'Overall feedback';
$string['criteriascores'] = 'Criteria scores';
$string['criterion'] = 'Criterion';
$string['autocalculated'] = 'Auto-calculated';
$string['autocalculated_hint'] = 'This value is automatically calculated from the sum of per-question scores. It cannot be edited directly.';
$string['citations'] = 'Citations from course materials';
$string['page'] = 'Page';
$string['confidence'] = 'AI confidence';
$string['retrieveddocs'] = 'Retrieved documents';
$string['nosource'] = 'Source not available';
$string['gradedby'] = 'Graded by AI RAG';
$string['gradedat'] = 'Graded at';

// Status.
$string['status_open'] = 'Open';
$string['status_closed'] = 'Closed';
$string['status_grading'] = 'Grading in progress';
$string['submissionstatus'] = 'Submission status';
$string['submitted'] = 'Submitted';
$string['notsubmitted'] = 'Not submitted';
$string['submittedcount'] = '{$a->submitted} of {$a->total} students submitted';

// Server.
$string['serverurl'] = 'RAG Server URL';
$string['serverurl_desc'] = 'The URL of the RAG API server (e.g., http://127.0.0.1:8000)';
$string['apikey'] = 'API Key (Optional)';
$string['apikey_desc'] = 'Optional bearer token matching API_AUTH_TOKEN on the RAG API server.';
$string['servererror'] = 'Could not connect to the RAG server. Please check the server URL in plugin settings.';

// Privacy.
$string['privacy:metadata'] = 'The AI RAG Assignment plugin stores student submissions and AI-generated grades.';

// Misc.
$string['search:activity'] = 'AI RAG Assignment';
$string['indicator:cognitivedepth'] = 'AI RAG Assignment cognitive';
$string['indicator:cognitivedepth_help'] = 'Cognitive depth indicator for AI RAG Assignment.';
$string['indicator:socialbreadth'] = 'AI RAG Assignment social';
$string['indicator:socialbreadth_help'] = 'Social breadth indicator for AI RAG Assignment.';
$string['backtoassignment'] = 'Back to assignment';
$string['allsubmissions'] = 'All submissions';
$string['student'] = 'Student';
$string['submitteddate'] = 'Submitted';
$string['grade'] = 'Grade';
$string['status'] = 'Status';
$string['actions'] = 'Actions';
$string['question'] = 'Question';
$string['answer'] = 'Answer';
$string['score'] = 'Score';
$string['feedback'] = 'Feedback';
$string['nosubmissions'] = 'No submissions yet.';
$string['duedatepassed'] = 'Due date has passed.';
$string['duedatenotpassed'] = 'Due date: {$a}';
$string['timeremaining'] = 'Time remaining: {$a}';
$string['description'] = 'Description';
$string['assignmentinfo'] = 'Assignment information';
$string['rubricinfo'] = 'Rubric';

// New form UX strings.
$string['assignmentname_placeholder'] = 'e.g. Chapter 5 - Deployment Pipeline Quiz';
$string['maximumgrade_error'] = 'Maximum grade must be at least 1.';
$string['selectmaterials_placeholder'] = '— Click or type to search and select materials —';
$string['materials_hint'] = 'Every selected material must finish vectorization (✓ [vectorized]) before AI grading can run. Tip: you can search by material name.';
$string['essayheader'] = 'Essay Mode Settings';
$string['essayprompt_required_hint'] = 'Required for Essay mode. Describe clearly what students must write about — this is the prompt shown to students.';
$string['essayprompt_placeholder'] = 'e.g. Write an essay explaining the deployment pipeline process, including stages from code commit to production deployment. Use concepts from the course materials.';
$string['essayprompt_required'] = 'Essay prompt is required for essay mode.';
$string['minmaxwords_hint'] = 'Set to 0 to disable this word count limit.';
$string['rubric_sumhint'] = 'Important: Total of all criterion scores MUST equal the Maximum Grade.';
$string['rubric_required_hint'] = 'At least 1 criterion is required. Fields marked (*) must be filled. Example: if Maximum Grade = 100, set scores to 40 + 35 + 25 = 100.';
$string['criterionname_placeholder'] = 'e.g. Relevance';
$string['criteriondesc_placeholder'] = 'e.g. How well the answer addresses the topic using course materials';
$string['rubric_score_mismatch'] = 'Total criterion scores ({$a->sum}) does not equal Maximum Grade ({$a->max}). Please adjust criterion scores so they sum to {$a->max}.';
$string['criterion_required_error'] = 'At least one rubric criterion is required.';
$string['questions_required_hint'] = 'Add at least 1 question. Students will answer each question individually, and the AI will grade each one. Questions are numbered automatically.';
$string['questionlabel'] = 'Question';
$string['question_placeholder'] = 'e.g. Explain what a deployment pipeline is and describe the main stages involved.';
$string['questions_required_error'] = 'At least one question is required for quiz mode.';

// ── Human-in-the-loop (HITL) grading strings ─────────────────────────────────
$string['hitl_info'] = 'Human-in-the-loop: The AI provides grading suggestions only. All final grades are set and confirmed by the teacher.';
$string['reviewaisuggestion'] = 'Review AI Suggestion';
$string['aisuggestion'] = 'AI Suggestion';
$string['aisuggested_grade'] = 'AI Suggested Grade';
$string['grademanually'] = 'Grade Manually';
$string['gradingform'] = 'Grading Form';
$string['grading_decision'] = 'Grading Decision';
$string['accept_ai_suggestion'] = 'Accept AI Suggestion';
$string['override_grade'] = 'Override with my own grade';
$string['finalgrade'] = 'Final Grade';
$string['confirmgrade'] = 'Confirm Grade';
$string['gradeaccepted'] = 'AI suggestion accepted and saved as the final grade.';
$string['gradeoverridden'] = 'Grade successfully overridden and saved.';
$string['savefinalgrade'] = 'Save Grade';
$string['ai_suggestion_pending'] = 'AI Suggestion Pending Review';
$string['ai_suggestions_pending'] = '{$a} submission(s) have AI suggestions awaiting your review.';
$string['aisuggestion_ready'] = 'AI suggestion ready for {$a}. Please review and confirm the grade.';
$string['aigrading_complete_review'] = 'AI grading complete. {$a->success} of {$a->total} submissions are ready for review.';
$string['aisuggestion_available'] = 'An AI suggestion is already available for this submission.';
$string['studentsubmission'] = 'Student Submission';
$string['teacher_note'] = 'Teacher note';
$string['teacher_note_internal'] = 'internal, not shown to students';
$string['teacher_note_placeholder'] = 'Optional: note for yourself about this grading decision...';
$string['perquestion_scores'] = 'Per-question scores';
$string['editgrade'] = 'Edit Grade';
$string['gradedby_ai_confirmed'] = 'AI suggestion accepted by teacher';
$string['gradedby_teacher'] = 'Graded manually by teacher';
$string['ai_original_suggestion'] = 'View original AI suggestion';
$string['teacher_override'] = 'Teacher Override';

// Bulk accept-all.
$string['acceptall_ai']           = 'Accept All AI Suggestions';
$string['acceptall_ai_confirm_title'] = 'Confirm: Accept All AI Suggestions';
$string['acceptall_ai_confirm_body']  = '<strong>Warning!</strong> You are about to accept <strong>{$a} AI suggestion(s)</strong> as final grades <strong>all at once</strong>, without reviewing each one individually. This action will immediately push all those grades to the gradebook and <strong>cannot be undone</strong>. Make sure you have verified that the AI suggestions are reasonable before proceeding.';
$string['acceptall_ai_confirm_check'] = 'I understand the consequences and want to accept all AI suggestions at once.';
$string['acceptall_complete']     = 'Done! {$a->success} of {$a->total} AI suggestions accepted as final grades.';
$string['acceptall_nothing']      = 'No AI suggestions are pending — nothing to accept.';
$string['acceptall_confirmation_required'] = 'Confirmation is required before accepting all AI suggestions.';
$string['grading_queued_single'] = 'AI grading for {$a} has been queued. You can navigate away and come back later.';
$string['grading_queued_bulk'] = 'AI grading for {$a} submission(s) has been queued. You can navigate away and come back later.';
$string['grading_processing_title'] = 'AI grading in progress';
$string['queue_navigate_away'] = 'You can navigate away and come back later.';

// Rubric source and manual file strings.
$string['rubricmode'] = 'Rubric source';
$string['rubricmode_help'] = 'Choose the rubric source. Custom Rubric allows defining criteria directly below. Moodle Native Rubric uses Moodle\'s built-in advanced grading rubric (configured via Grade administration).';
$string['rubricmode_custom'] = 'Custom Rubric (Activity Built-in)';
$string['rubricmode_moodle'] = 'Moodle Native Rubric (Advanced Grading)';
$string['moodlerubric_info_text'] = 'You have selected Moodle Native Rubric. After saving this assignment, please go to **Advanced Grading** in the settings menu of this activity to define or select the active rubric.';
$string['manualfile'] = 'Manual Reference / Answer Key File';
$string['manualfile_help'] = 'Upload a manual file (PDF, PPTX, DOCX, TXT), such as a model answer key or reference handbook, to be used specifically as additional context for grading.';
$string['submissions'] = 'Submissions';
$string['submissions_help'] = 'Students\' answers and submissions context';
$string['gradeitem:submissions'] = 'Submissions';
$string['knowledgebase_required_error'] = 'At least one of "Select course materials" or "Manual Reference / Answer Key File" must be provided.';
$string['linkedmaterials_no_vectorized_files'] = 'None of the files in the linked course materials are vectorized. Re-run vectorization on the materials, then retry grading.';
$string['linkedmaterials_not_ready'] = 'Linked course materials are not ready for grading: {$a}. Wait for queued or processing materials to finish, and re-vectorize or unlink pending or failed ones, then retry grading.';
$string['manualfile_vectorize_failed'] = 'The manual reference file could not be vectorized on the RAG server: {$a}. Grading will not find evidence in this file until it is uploaded again successfully.';
