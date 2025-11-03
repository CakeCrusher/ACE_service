import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '../api/client'

const DEFAULT_PROMPT = 'How do I solve this math problem?'
const DEFAULT_PLAYBOOK_ID = ''

const DEFAULT_EMBED_BODY = JSON.stringify({
  prompt: DEFAULT_PROMPT,
  k: 20
}, null, 2)

const DEFAULT_LEARN_BODY = JSON.stringify({
  user_message: 'Write Python code to parse a CSV file and return the rows as a list of dictionaries.',
  trajectory: `=== INITIAL INPUT ===
Write Python code to parse a CSV file and return the rows as a list of dictionaries.

---

You are also provided with a curated cheatsheet of strategies, common mistakes, and proven solutions to help you solve the task effectively.

**ACE Playbook:** – Read the **Playbook** first, then execute the task by explicitly leveraging each relevant section:

**PLAYBOOK_BEGIN**

- [bullet-001] helpful=2 harmful=0 :: Always handle file I/O with proper context managers (with statements)
- [bullet-002] helpful=1 harmful=0 :: Use list comprehensions for concise data transformation

**PLAYBOOK_END**

=== TOOL CALLS / REASONING ===
Step 1: Understand the task - parse CSV and convert to list of dictionaries
Step 2: Apply bullet-001 - use context manager for file handling
Step 3: Apply bullet-002 - use list comprehension for transformation
Step 4: Write the code implementation

Here's my implementation:

\`\`\`python
def parse_csv(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()

    # Get headers from first line
    headers = lines[0].strip().split(',')

    # Parse data rows
    data = []
    for line in lines[1:]:
        values = line.strip().split(',')
        row_dict = {headers[i]: values[i] for i in range(len(headers))}
        data.append(row_dict)

    return data
\`\`\`

=== FINAL OUTPUT ===
\`\`\`python
def parse_csv(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()

    # Get headers from first line
    headers = lines[0].strip().split(',')

    # Parse data rows
    data = []
    for line in lines[1:]:
        values = line.strip().split(',')
        row_dict = {headers[i]: values[i] for i in range(len(headers))}
        data.append(row_dict)

    return data
\`\`\`
`,
  ground_truth: 'The code should handle quoted CSV fields containing commas (e.g., "John, Jr.", "Manager") correctly using csv.DictReader or proper quote handling.',
  evaluation: 'The code fails on CSV files with quoted fields containing commas. For example, a row like \'Name,"Address, City",Age\' would be incorrectly split at the comma inside the quotes. The code needs to use Python\'s csv module or implement proper quote handling.',
  reflector_additional_instructions: null,
  curator_additional_instructions: null
}, null, 2)

export default function Playground() {
  const [embedPlaybookId, setEmbedPlaybookId] = useState(DEFAULT_PLAYBOOK_ID)
  const [embedBody, setEmbedBody] = useState(DEFAULT_EMBED_BODY)

  const [learnPlaybookId, setLearnPlaybookId] = useState(DEFAULT_PLAYBOOK_ID)
  const [learnBody, setLearnBody] = useState(DEFAULT_LEARN_BODY)
  const [learnJobId, setLearnJobId] = useState<string | null>(null)

  const embedMutation = useMutation({
    mutationFn: async () => {
      const body = JSON.parse(embedBody)
      const response = await api.embedPrompt(embedPlaybookId, body)
      return response.data
    },
  })

  const learnMutation = useMutation({
    mutationFn: async () => {
      const body = JSON.parse(learnBody)
      const response = await api.startLearn(learnPlaybookId, body)
      return response.data
    },
    onSuccess: (data) => {
      setLearnJobId(data.learn_job_id)
    },
  })

  const { data: learnJobResponse } = useQuery({
    queryKey: ['learnJob', learnPlaybookId, learnJobId],
    queryFn: async () => {
      if (!learnJobId || !learnPlaybookId) return null
      const response = await api.getLearnJob(learnPlaybookId, learnJobId)
      return response.data
    },
    enabled: !!learnJobId && !!learnPlaybookId,
    refetchInterval: (query) => {
      // Poll every 2 seconds if job is still running
      const learnJob = query.state.data?.learn_job
      return learnJob?.status === 'running' || learnJob?.status === 'pending' ? 2000 : false
    },
  })

  const learnJob = learnJobResponse?.learn_job

  return (
    <div className="px-4 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Playground</h1>

      <div className="space-y-8">
        {/* Embed Prompt Section */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Embed Prompt</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Playbook ID
              </label>
              <input
                type="text"
                value={embedPlaybookId}
                onChange={(e) => setEmbedPlaybookId(e.target.value)}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="Enter playbook ID..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Request Body (JSON)
              </label>
              <textarea
                value={embedBody}
                onChange={(e) => setEmbedBody(e.target.value)}
                rows={10}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm font-mono text-xs"
                placeholder='{"prompt": "Your prompt here", "k": 20}'
              />
              {(() => {
                try {
                  JSON.parse(embedBody)
                  return null
                } catch {
                  return (
                    <p className="mt-1 text-sm text-red-600">Invalid JSON</p>
                  )
                }
              })()}
            </div>
            <button
              onClick={() => embedMutation.mutate()}
              disabled={embedMutation.isPending || !embedPlaybookId || !embedBody}
              className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:opacity-50"
            >
              {embedMutation.isPending ? 'Embedding...' : 'Embed Prompt'}
            </button>
            {embedMutation.isError && (
              <div className="mt-4 text-sm text-red-600">
                Error: {embedMutation.error instanceof Error ? embedMutation.error.message : 'Unknown error'}
              </div>
            )}
            {embedMutation.isSuccess && embedMutation.data && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Embedded Result
                </label>
                <div className="bg-gray-50 border rounded-md p-4">
                  <pre className="whitespace-pre-wrap text-sm text-gray-900">{embedMutation.data.prompt}</pre>
                </div>
                <button
                  onClick={() => navigator.clipboard.writeText(embedMutation.data.prompt)}
                  className="mt-2 text-sm text-indigo-600 hover:text-indigo-900"
                >
                  Copy to Clipboard
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Learn Workflow Section */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Run Learn Workflow</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Playbook ID
              </label>
              <input
                type="text"
                value={learnPlaybookId}
                onChange={(e) => setLearnPlaybookId(e.target.value)}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="Enter playbook ID..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Request Body (JSON)
              </label>
              <p className="text-xs text-gray-500 mb-2">
                Note: The trajectory should contain: (1) the initial input with embedded prompt containing <strong>**PLAYBOOK_BEGIN**</strong> and <strong>**PLAYBOOK_END**</strong> markers, (2) tool calls/reasoning, and (3) final output. The playbook will be automatically extracted from the markers in the initial input.
              </p>
              <textarea
                value={learnBody}
                onChange={(e) => setLearnBody(e.target.value)}
                rows={15}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm font-mono text-xs"
                placeholder='{"user_message": "...", "trajectory": "... (with PLAYBOOK_BEGIN/PLAYBOOK_END markers)", ...}'
              />
              {(() => {
                try {
                  JSON.parse(learnBody)
                  return null
                } catch {
                  return (
                    <p className="mt-1 text-sm text-red-600">Invalid JSON</p>
                  )
                }
              })()}
            </div>
            <button
              onClick={() => learnMutation.mutate()}
              disabled={learnMutation.isPending || !learnPlaybookId || !learnBody}
              className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:opacity-50"
            >
              {learnMutation.isPending ? 'Starting...' : 'Start Learn Workflow'}
            </button>
            {learnMutation.isError && (
              <div className="mt-4 text-sm text-red-600">
                Error: {learnMutation.error instanceof Error ? learnMutation.error.message : 'Unknown error'}
              </div>
            )}
            {learnJobId && (
              <div className="mt-4">
                <div className="bg-blue-50 border border-blue-200 rounded-md p-4">
                  <p className="text-sm font-medium text-blue-900">
                    Learn Job Started: <span className="font-mono">{learnJobId}</span>
                  </p>
                </div>
              </div>
            )}
            {learnJob && (
              <div className="mt-4 space-y-4">
                <div className={`border rounded-md p-4 ${
                  learnJob.status === 'completed' ? 'bg-green-50 border-green-200' :
                  learnJob.status === 'failed' ? 'bg-red-50 border-red-200' :
                  'bg-yellow-50 border-yellow-200'
                }`}>
                  <h3 className="text-sm font-semibold text-gray-900 mb-2">Job Status</h3>
                  <p className="text-sm">
                    Status: <span className="font-medium">{learnJob.status}</span>
                  </p>
                  {learnJob.error && (
                    <p className="text-sm text-red-600 mt-2">Error: {learnJob.error}</p>
                  )}
                </div>
                {learnJob.reflection && (
                  <div className="bg-gray-50 border rounded-md p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-2">Reflection</h3>
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap">
                      {JSON.stringify(learnJob.reflection, null, 2)}
                    </pre>
                  </div>
                )}
                {learnJob.curation && (
                  <div className="bg-gray-50 border rounded-md p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-2">Curation</h3>
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap">
                      {JSON.stringify(learnJob.curation, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
