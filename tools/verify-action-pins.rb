#!/usr/bin/env ruby
# frozen_string_literal: true

require "psych"

IMMUTABLE_ACTION = /\A[^@\s]+@[0-9a-f]{40}\z/

class WorkflowError < StandardError; end

def scalar_value(node, label, path)
  return node.value if node.is_a?(Psych::Nodes::Scalar)

  raise WorkflowError, "#{label}: #{path} must be a scalar"
end

def inspect_node(node, label, path, action_refs)
  case node
  when Psych::Nodes::Stream, Psych::Nodes::Document
    node.children.each { |child| inspect_node(child, label, path, action_refs) }
  when Psych::Nodes::Sequence
    node.children.each_with_index do |child, index|
      inspect_node(child, label, "#{path}[#{index}]", action_refs)
    end
  when Psych::Nodes::Mapping
    seen = {}
    node.children.each_slice(2) do |key_node, value_node|
      key = scalar_value(key_node, label, path)
      key_path = path == "$" ? "$.#{key}" : "#{path}.#{key}"
      raise WorkflowError, "#{label}: duplicate mapping key at #{key_path}" if seen[key]
      raise WorkflowError, "#{label}: YAML merge keys are not allowed at #{key_path}" if key == "<<"

      seen[key] = true
      if key == "uses"
        reference = scalar_value(value_node, label, key_path)
        unless reference.start_with?("./") || IMMUTABLE_ACTION.match?(reference)
          raise WorkflowError,
                "#{label}: third-party action at #{key_path} must use full commit SHAs " \
                "(40-character): #{reference}"
        end
        action_refs << reference
      end
      inspect_node(value_node, label, key_path, action_refs)
    end
  when Psych::Nodes::Alias
    raise WorkflowError, "#{label}: YAML aliases are not allowed at #{path}"
  end
end

begin
  inputs = ARGV.empty? ? Dir.glob(".github/workflows/*.{yml,yaml}").sort : ARGV
  raise WorkflowError, "no workflow files found" if inputs.empty?

  action_refs = []
  inputs.each do |input|
    label = input == "-" ? "<stdin>" : input
    source = input == "-" ? $stdin.read : File.read(input, encoding: "UTF-8")
    document = Psych.parse_stream(source)
    inspect_node(document, label, "$", action_refs)
  rescue Psych::SyntaxError => error
    raise WorkflowError, "#{label}: invalid YAML: #{error.message}"
  end

  puts action_refs
  warn "Verified #{inputs.length} workflow file(s) and #{action_refs.length} action reference(s)."
rescue WorkflowError => error
  warn error.message
  exit 1
end
