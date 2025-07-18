import React, { useState } from 'react';
import type { TaskFormData, DataSourceCheckboxState, DataSourceIdentifier } from '../types';
import { getCheckboxStateFromString, getDataSourcePreferenceString } from '../utils/timelineUtils';
import { useAuth } from '../contexts/auth';

interface TaskFormProps {
  onSubmit: (formData: TaskFormData) => void;
  isSubmitting: boolean;
  error: string | null;
}

const TaskForm: React.FC<TaskFormProps> = ({ onSubmit, isSubmitting, error }) => {
  const { user } = useAuth();
  const [topic, setTopic] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [dataSources, setDataSources] = useState<DataSourceCheckboxState>(
    getCheckboxStateFromString('dataset_wikipedia_en=true')
  );

  const handleDataSourceToggle = (sourceKey: DataSourceIdentifier, checked: boolean) => {
    setDataSources((prev: DataSourceCheckboxState) => ({
      ...prev,
      [sourceKey]: checked,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) {
      // Basic validation, though the 'required' attribute on input is primary
      return;
    }
    const dataSourceString = getDataSourcePreferenceString(dataSources);
    onSubmit({
      topic_text: topic,
      data_source_pref: dataSourceString,
      is_public: user ? isPublic : undefined,
    });
  };

  const dataSourceOptions: { key: DataSourceIdentifier; label: string; description: string }[] = [
    {
      key: 'dataset_wikipedia_en',
      label: 'Dataset Wikipedia of English',
      description: 'A vast, locally-stored snapshot of English Wikipedia.',
    },
    {
      key: 'online_wikipedia',
      label: 'Online Wikipedia',
      description:
        'Current, live articles from the global encyclopedia, including the input-language and English articles.',
    },
    {
      key: 'online_wikinews',
      label: 'Online Wikinews',
      description: 'Recent and archived news reports, including the input-language.',
    },
  ];

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      <div>
        <label
          htmlFor="topic"
          className="block text-lg font-sans font-medium text-charcoal dark:text-white mb-2"
        >
          I. Define Your Subject of Inquiry
        </label>
        <p className="text-slate dark:text-mist mb-4">
          Enter the historical topic, event, or question you wish to investigate. Be as specific as
          possible for a more focused chronicle.
        </p>
        <textarea
          id="topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          className="w-full bg-white dark:bg-slate border border-pewter rounded-md p-3 text-charcoal dark:text-mist placeholder-pewter focus:ring-1 focus:ring-slate focus:border-slate dark:focus:ring-sky-blue dark:focus:border-sky-blue transition"
          placeholder="e.g., The economic impact of the Silk Road during the Tang Dynasty"
          required
          disabled={isSubmitting}
          rows={3}
          maxLength={1000}
        />
        <p className="text-right text-xs text-pewter mt-1">{topic.length} / 1000</p>
      </div>

      <div>
        <label className="block text-lg font-sans font-medium text-charcoal dark:text-white mb-2">
          II. Select Primary Sources
        </label>
        <p className="text-slate dark:text-mist mb-4">
          Choose the archives from which to draw information for your chronicle. At least one source
          is required.
        </p>
        <div className="space-y-4">
          {dataSourceOptions.map(({ key, label, description }) => (
            <div
              key={key}
              className="relative flex items-start bg-mist/30 dark:bg-slate/30 p-4 border border-mist dark:border-pewter rounded-lg"
            >
              <div className="flex h-6 items-center">
                <input
                  id={key}
                  name={key}
                  type="checkbox"
                  checked={dataSources[key]}
                  onChange={(e) => handleDataSourceToggle(key, e.target.checked)}
                  disabled={isSubmitting}
                  className="h-5 w-5 rounded border-pewter text-slate dark:text-sky-blue focus:ring-slate dark:focus:ring-sky-blue"
                />
              </div>
              <div className="ml-3 text-sm leading-6">
                <label htmlFor={key} className="font-medium text-charcoal dark:text-white">
                  {label}
                </label>
                <p className="text-slate dark:text-mist">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {user && (
        <div>
          <label className="block text-lg font-sans font-medium text-charcoal dark:text-white mb-2">
            III. Set Visibility
          </label>
          <div className="relative flex items-start bg-mist/30 dark:bg-slate/30 p-4 border border-mist dark:border-pewter rounded-lg">
            <div className="flex h-6 items-center">
              <input
                id="is_public"
                name="is_public"
                type="checkbox"
                checked={isPublic}
                onChange={(e) => setIsPublic(e.target.checked)}
                disabled={isSubmitting}
                className="h-5 w-5 rounded border-pewter text-slate dark:text-sky-blue focus:ring-slate dark:focus:ring-sky-blue"
              />
            </div>
            <div className="ml-3 text-sm leading-6">
              <label htmlFor="is_public" className="font-medium text-charcoal dark:text-white">
                Make this Chronicle Public
              </label>
              <p className="text-slate dark:text-mist">
                Allow anyone to view the generated timeline. If unchecked, it will be private.
              </p>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-md">
          <p className="font-bold">An Error Occurred</p>
          <p>{error}</p>
        </div>
      )}

      <div className="text-center pt-4 border-t-2 border-dashed border-mist dark:border-pewter">
        <button
          type="submit"
          disabled={isSubmitting || !topic.trim()}
          className="btn btn-primary font-bold py-3 px-12 rounded-lg shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all duration-200 disabled:bg-gray-400 disabled:shadow-none disabled:transform-none disabled:cursor-not-allowed"
        >
          {isSubmitting ? 'Initiating Research...' : 'Create Chronicle'}
        </button>
      </div>
    </form>
  );
};

export default TaskForm;
