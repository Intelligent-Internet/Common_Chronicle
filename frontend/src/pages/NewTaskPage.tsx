import React, { useState, useCallback } from 'react';
import TaskForm from '../components/TaskForm';
import type { TaskFormData } from '../types';
import { createTask } from '../services/api';
import ParchmentPaper from '../components/ParchmentPaper';
import WavyLine from '../components/WavyLine';

const NewTaskPage: React.FC = () => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submissionSuccess, setSubmissionSuccess] = useState(false);
  const [formKey, setFormKey] = useState(Date.now());

  const handleFormSubmit = useCallback(async (formData: TaskFormData) => {
    setIsSubmitting(true);
    setError(null);

    // Open a new tab immediately in response to the user's click
    // This is less likely to be blocked by pop-up blockers.
    const newTab = window.open('', '_blank');

    try {
      const createdTask = await createTask({
        topic_text: formData.topic_text,
        config: {
          data_source_preference: formData.data_source_pref,
        },
        is_public: formData.is_public,
      });

      // Now set the URL of the new tab
      if (newTab) {
        newTab.location.href = `/task/${createdTask.id}`;
      } else {
        // This case handles if the user's browser settings are extremely strict
        // and even blocked the initial `window.open`.
        throw new Error(
          "Failed to open new tab. Please check your browser's pop-up blocker settings."
        );
      }

      // Set submission success state
      setSubmissionSuccess(true);
    } catch (err) {
      // If something goes wrong, close the blank tab.
      if (newTab) {
        newTab.close();
      }

      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const handleCreateAnother = useCallback(() => {
    setSubmissionSuccess(false);
    setError(null);
    setFormKey(Date.now()); // Reset form by changing key
  }, []);

  const renderSuccessMessage = () => (
    <div className="text-center py-12">
      <div className="mb-8">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
          <svg
            className="w-8 h-8 text-green-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 className="text-3xl font-serif text-scholar-800 mb-4">Task Submitted Successfully!</h2>
        <p className="text-lg text-scholar-600 mb-2">
          Your chronicle task has been submitted and is now being processed in a new tab.
        </p>
        <p className="text-sm text-scholar-500">
          Switch to the new tab to monitor the processing progress, or continue submitting more
          tasks here.
        </p>
      </div>

      <div className="max-w-md mx-auto mb-6">
        <WavyLine className="text-parchment-400" />
      </div>

      <button
        onClick={handleCreateAnother}
        className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-scholar-600 hover:bg-scholar-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-scholar-500 transition-colors duration-200"
      >
        <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Submit Another Task
      </button>
    </div>
  );

  return (
    <div className="min-h-screen py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-10">
          <h1 className="text-5xl font-serif text-scholar-800">Submit a New Chronicle Task</h1>
          <p className="mt-4 text-lg text-scholar-600">
            Define the subject of your historical inquiry to generate a timeline.
          </p>
          <div className="mt-6 max-w-md mx-auto">
            <WavyLine className="text-parchment-400" />
          </div>
        </div>

        <ParchmentPaper>
          {submissionSuccess ? (
            renderSuccessMessage()
          ) : (
            <TaskForm
              key={formKey}
              onSubmit={handleFormSubmit}
              isSubmitting={isSubmitting}
              error={error}
            />
          )}
        </ParchmentPaper>
      </div>
    </div>
  );
};

export default NewTaskPage;
