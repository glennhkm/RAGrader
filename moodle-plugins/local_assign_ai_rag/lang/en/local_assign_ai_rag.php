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
 * Language strings for local_assign_ai_rag (English).
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$string['pluginname'] = 'RAG Assignment AI Grading';
$string['privacy:metadata'] = 'The RAG Assignment AI plugin stores pending AI grades temporarily.';

// Settings page.
$string['settings'] = 'RAG Assignment AI Settings';
$string['serverheading'] = 'RAG Server Configuration';
$string['serverheading_desc'] = 'Configure the connection to the RAG grading server.';
$string['serverurl'] = 'Server URL';
$string['serverurl_desc'] = 'The URL of the RAG grading server (e.g., http://localhost:8000).';
$string['apikey'] = 'API Key';
$string['apikey_desc'] = 'Optional API key for authentication with the RAG server.';
$string['timeout'] = 'Request Timeout';
$string['timeout_desc'] = 'Maximum time in seconds to wait for a response from the RAG server.';
$string['gradingheading'] = 'Default Grading Settings';
$string['gradingheading_desc'] = 'Default settings for new assignments.';
$string['defaultautograde'] = 'Enable auto-grading by default';
$string['defaultautograde_desc'] = 'When enabled, new assignments will have auto-grading enabled by default.';
$string['defaultusematerials'] = 'Use course materials by default';
$string['defaultusematerials_desc'] = 'When enabled, new assignments will use course materials (RAG) by default.';

// Assignment form settings.
$string['aiconfigheader'] = 'RAG AI Grading Configuration';
$string['autograde'] = 'Enable RAG AI Auto-grading';
$string['autograde_help'] = 'When enabled, submissions will be automatically graded using RAG AI with course materials as context.';
$string['usecoursematerials'] = 'Use Course Materials (RAG)';
$string['usecoursematerials_help'] = 'When enabled, the AI will use uploaded course materials to provide context-aware grading with citations.';
$string['autogradegrader'] = 'Grader for AI grades';
$string['autogradegrader_help'] = 'Select the user who will be recorded as the grader for AI-generated grades.';

// Status messages.
$string['processing'] = 'Processing with RAG AI...';
$string['gradingcomplete'] = 'AI grading complete.';
$string['gradingerror'] = 'Error during AI grading: {$a}';
$string['serverunavailable'] = 'RAG server is unavailable. Please try again later.';

// UI strings.
$string['reviewwithai'] = 'Review with RAG AI';
$string['reviewhistory'] = 'AI Review History';
$string['reviewall'] = 'Review all pending';
$string['approve'] = 'Approve';
$string['reject'] = 'Reject';
$string['pending'] = 'Pending review';
$string['approved'] = 'Approved';
$string['rejected'] = 'Rejected';
$string['initial'] = 'Not reviewed';
$string['queued'] = 'Queued';

// Grading.
$string['aigrade'] = 'AI Grade';
$string['aifeedback'] = 'AI Feedback';
$string['confidence'] = 'Confidence Score';
$string['citations'] = 'Citations from course materials';
$string['nocitations'] = 'No citations available.';
$string['retrieveddocs'] = 'Retrieved documents';
$string['default_rubric_name'] = 'Assignment Rubric';

// Materials.
$string['uploadmaterials'] = 'Upload course materials';
$string['uploadmaterials_desc'] = 'Upload PDF/PPTX files to use as grading context.';
$string['materialscount'] = 'Materials in knowledge base: {$a}';
$string['nomaterials'] = 'No course materials uploaded yet.';
$string['clearmaterials'] = 'Clear all materials';
$string['clearmaterialsconfirm'] = 'Are you sure you want to clear all course materials? This cannot be undone.';
$string['materialsmanagement'] = 'Course Materials Management';

// Tasks.
$string['taskprocesssubmission'] = 'Process submission with RAG AI';
$string['taskprocessall'] = 'Process all pending submissions';

// Events.
$string['eventsubmissiongraded'] = 'Submission graded by AI';
$string['eventsubmissionapproved'] = 'AI grade approved';
$string['eventsubmissionrejected'] = 'AI grade rejected';

// Review page.
$string['reviewpage'] = 'AI Review';
$string['reviewpagetitle'] = 'Review Submissions with RAG AI';
$string['nosubmissions'] = 'No submissions to review.';
$string['student'] = 'Student';
$string['submissionstatus'] = 'Submission Status';
$string['aistatus'] = 'AI Status';
$string['actions'] = 'Actions';
$string['viewdetails'] = 'View Details';
$string['reviewsubmission'] = 'Review with AI';
$string['approvegrade'] = 'Approve Grade';
$string['rejectgrade'] = 'Reject Grade';

// Errors.
$string['error:nosubmission'] = 'Submission not found.';
$string['error:notsubmitted'] = 'Submission has not been submitted.';
$string['error:alreadygraded'] = 'Submission has already been graded.';
$string['error:serverconnection'] = 'Could not connect to RAG server.';
$string['error:invalidresponse'] = 'Invalid response from RAG server.';
$string['error:invaliduploadfile'] = 'The material upload contains an invalid file.';
$string['error:materialuploadfailed'] = 'Could not upload material: {$a}';
$string['error:nopermission'] = 'You do not have permission to perform this action.';

// Review action messages.
$string['reviewsuccess'] = 'Submission has been reviewed by AI. Check the results below.';
$string['reviewerror'] = 'Error during AI review';

// View result page.
$string['viewresult'] = 'AI Grading Result';
$string['backtoreview'] = 'Back to Review';
$string['studentinfo'] = 'Student Information';
$string['name'] = 'Name';
$string['email'] = 'Email';
$string['submissiontime'] = 'Submission Time';
$string['submittedfiles'] = 'Submitted Files';
$string['onlinetext'] = 'Online Text';
$string['airesult'] = 'AI Grading Result';
$string['status'] = 'Status';
$string['feedback'] = 'Feedback';
$string['criterionscores'] = 'Criterion Scores';
$string['criterion'] = 'Criterion';
$string['score'] = 'Score';
$string['assignment'] = 'Assignment';
$string['approvehint'] = 'Approving will push the AI grade and feedback to the student\'s gradebook.';
$string['gradeapproved'] = 'Grade has been approved and pushed to student.';
$string['graderejected'] = 'Grade rejected. The submission has been reset for re-review.';
$string['alreadyapproved'] = 'This grade has already been approved and pushed to the student.';
$string['notreviewedyet'] = 'This submission has not been reviewed with AI yet. Please review first.';

// Rubric editor.
$string['rubriceditor'] = 'RAG Rubric Editor';
$string['rubricinfo'] = 'Custom Rubric for RAG AI Grading';
$string['rubricinfodesc'] = 'Define a custom rubric that will be used by the RAG AI for grading. Each criterion should have points, description, and level definitions.';
$string['maxgrade'] = 'Maximum Grade';
$string['maxgradehint'] = 'The total maximum grade for this assignment.';
$string['rubriccriteria'] = 'Rubric Criteria';
$string['addcriterion'] = 'Add Criterion';
$string['rubricjson'] = 'Rubric JSON (Advanced)';
$string['rubricjsonhint'] = 'You can directly edit the JSON if you prefer. Changes will sync with the visual editor.';
$string['saverubric'] = 'Save Rubric';
$string['resettodefault'] = 'Reset to Default';
$string['deleterubric'] = 'Delete Rubric';
$string['confirmdelete'] = 'Are you sure you want to delete this rubric?';
$string['rubricsaved'] = 'Rubric saved successfully.';
$string['rubricdeleted'] = 'Rubric deleted.';
$string['invalidjson'] = 'Invalid JSON format. Please check your rubric.';
$string['invalidrubricstructure'] = 'Invalid rubric structure. Must have a "criteria" object.';
$string['exampleformat'] = 'Example Rubric Format';
$string['editrubric'] = 'Edit Rubric';
