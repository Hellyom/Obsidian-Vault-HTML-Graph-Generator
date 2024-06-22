import os
import markdown
import json
import re
from collections import defaultdict
import tkinter as tk
from tkinter import filedialog, messagebox

# Global variables to store directories
vault_dir = None
output_dir = None

def parse_vault(vault_dir):
    notes = {}
    links = defaultdict(list)
    
    for root, _, files in os.walk(vault_dir):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    html_content = markdown.markdown(content)
                    notes[file.lower()] = {"content": content, "html": html_content}

                    link_patterns = [
                        r'\[\[(.*?)\]\]',
                        r'\[([^\]]+)\]\(([^)]+)\)',
                        r'!\[\[(.*?)\]\]'
                    ]

                    for pattern in link_patterns:
                        for match in re.finditer(pattern, content):
                            link = match.group(1)
                            link = link.split('|')[0]
                            link = link.split('#')[0]
                            link = link.strip().lower()
                            links[file.lower()].append(link)

    return notes, links

def generate_graph_data(notes, links, color_groups):
    def capitalize_first_letter(s):
        return s[0].upper() + s[1:] if s else s

    nodes = [{"id": note, "label": capitalize_first_letter(os.path.splitext(note)[0]), "content": notes[note]["content"]} for note in notes.keys()]
    edges = []

    node_link_count = defaultdict(int)
    for src, dst_list in links.items():
        node_link_count[src] += len(dst_list)
        for dst in dst_list:
            potential_targets = [
                dst,
                dst + '.md',
                os.path.splitext(dst)[0] + '.md'
            ]
            matched = False
            for target in potential_targets:
                if target in notes:
                    edges.append({"source": src, "target": target})
                    node_link_count[target] += 1
                    matched = True
                    break

    for node in nodes:
        node['link_count'] = node_link_count[node['id']]
        node['color'] = get_node_color(node, color_groups)

    for node in nodes:
        del node['content']

    return nodes, edges

def get_node_color(node, color_groups):
    content = node['content']
    for group in color_groups:
        if group['query'] and re.search(group['query'], content, re.IGNORECASE):
            return group['color']
    return "#7f7f7f"

def rgb_to_hex(rgb):
    return f"#{rgb:06x}"

def get_obsidian_colors(vault_dir):
    graph_config_path = os.path.join(vault_dir, '.obsidian', 'graph.json')
    try:
        with open(graph_config_path, 'r') as f:
            graph_config = json.load(f)
        color_groups = graph_config.get('colorGroups', [])
        for group in color_groups:
            group['color'] = rgb_to_hex(group['color']['rgb'])
        return color_groups
    except Exception as e:
        return []

def create_html_file(nodes, edges, color_groups, output_dir):
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { margin: 0; padding: 0; overflow: hidden; background-color: #1e1e1e; }
            .node { cursor: move; }
            .link { stroke: #999; stroke-opacity: 0.6; }
            text { font-family: Arial, sans-serif; font-size: 12px; pointer-events: none; fill: #fff; }
            svg { width: 100vw; height: 100vh; }
        </style>
    </head>
    <body>
        <div id="graph"></div>
        <script src="https://d3js.org/d3.v5.min.js"></script>
        <script>
            var nodes = """ + json.dumps(nodes) + """;
            var links = """ + json.dumps(edges) + """;
            var colorGroups = """ + json.dumps(color_groups) + """;

            var width = window.innerWidth;
            var height = window.innerHeight;

            var svg = d3.select("#graph")
                .append("svg")
                .attr("width", width)
                .attr("height", height);

            var g = svg.append("g");

            var zoom = d3.zoom()
                .scaleExtent([0.1, 4])
                .on("zoom", zoomed);

            svg.call(zoom);

            function zoomed() {
                g.attr("transform", d3.event.transform);
            }

            function customForce(alpha) {
                const centerX = width / 2;
                const centerY = height / 2;
                const strength = 0.05;

                for (let i = 0; i < nodes.length; i++) {
                    const node = nodes[i];
                    node.vx += (centerX - node.x) * strength * alpha;
                    node.vy += (centerY - node.y) * strength * alpha;
                }
            }

            var simulation = d3.forceSimulation(nodes)
                .force("link", d3.forceLink(links).id(d => d.id).distance(d => {
                    const sourceLinks = links.filter(link => link.source.id === d.source.id || link.target.id === d.source.id).length;
                    const targetLinks = links.filter(link => link.source.id === d.target.id || link.target.id === d.target.id).length;
                    return Math.min(150, Math.max(50, (sourceLinks + targetLinks) * 10));
                }))
                .force("charge", d3.forceManyBody().strength(-300))
                .force("center", d3.forceCenter(width / 2, height / 2))
                .force("custom", customForce)
                .force("collision", labelCollision())
                .alphaDecay(0.02)
                .alphaMin(0.001)
                .on("tick", ticked);

            var link = g.append("g")
                .attr("class", "links")
                .selectAll("line")
                .data(links)
                .enter().append("line")
                .attr("class", "link");

            var node = g.append("g")
                .attr("class", "nodes")
                .selectAll("circle")
                .data(nodes)
                .enter().append("circle")
                .attr("class", "node")
                .attr("r", function(d) {
                    var radius = 5 + Math.sqrt(d.link_count);
                    return radius;
                })
                .attr("fill", function(d) {
                    return d.color;
                })
                .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended));

            var text = g.append("g")
                .attr("class", "texts")
                .selectAll("text")
                .data(nodes)
                .enter().append("text")
                .attr("x", 8)
                .attr("y", ".31em")
                .text(d => d.label);

            function ticked() {
                link
                    .attr("x1", d => d.source.x)
                    .attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x)
                    .attr("y2", d => d.target.y);

                node
                    .attr("cx", d => d.x)
                    .attr("cy", d => d.y);

                text
                    .attr("x", d => d.x + 8)
                    .attr("y", d => d.y + 3);
            }

            function dragstarted(d) {
                if (!d3.event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            }

            function dragged(d) {
                d.fx = d3.event.x;
                d.fy = d3.event.y;
            }

            function dragended(d) {
                if (!d3.event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }

            function labelCollision() {
                var alpha = 0.5;
                return function() {
                    for (var i = 0; i < nodes.length; i++) {
                        for (var j = i + 1; j < nodes.length; j++) {
                            var nodeA = nodes[i];
                            var nodeB = nodes[j];
                            if (nodeA === nodeB) continue;

                            var dx = nodeA.x - nodeB.x;
                            var dy = nodeA.y - nodeB.y;
                            var distance = Math.sqrt(dx * dx + dy * dy);
                            var minDistance = 20;

                            if (distance < minDistance) {
                                var moveFactor = (minDistance - distance) / distance * alpha;
                                var mx = dx * moveFactor;
                                var my = dy * moveFactor;
                                nodeA.x += mx;
                                nodeA.y += my;
                                nodeB.x -= mx;
                                nodeB.y -= my;
                            }
                        }
                    }
                };
            }

        </script>
    </body>
    </html>
    """

    output_file = os.path.join(output_dir, 'vault_graph.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return os.path.abspath(output_file)

def create_html():
    global vault_dir, output_dir
    if not vault_dir:
        messagebox.showerror("Error", "Please select the vault directory first.")
        return
    if not output_dir:
        messagebox.showerror("Error", "Please select the output directory first.")
        return

    try:
        notes, links = parse_vault(vault_dir)
        color_groups = get_obsidian_colors(vault_dir)
        nodes, edges = generate_graph_data(notes, links, color_groups)
        output_file = create_html_file(nodes, edges, color_groups, output_dir)
        messagebox.showinfo("Success", f"HTML file created: {output_file}")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {e}")

def select_vault_directory():
    global vault_dir
    vault_dir = filedialog.askdirectory(title="Select Obsidian Vault Directory")
    if vault_dir:
        messagebox.showinfo("Vault Directory", f"Vault directory selected: {vault_dir}")

def select_output_directory():
    global output_dir
    output_dir = filedialog.askdirectory(title="Select Output Directory")
    if output_dir:
        messagebox.showinfo("Output Directory", f"Output directory selected: {output_dir}")

def open_support_link():
    import webbrowser
    webbrowser.open("https://buymeacoffee.com/oscarch")

# GUI Setup
root = tk.Tk()
root.title("Obsidian Vault Graph Generator")
root.geometry("300x250")
root.resizable(False, False)

frame = tk.Frame(root)
frame.pack(pady=20)

btn_select_vault = tk.Button(frame, text="Select Vault Directory", command=select_vault_directory)
btn_select_vault.pack(pady=10)

btn_select_output = tk.Button(frame, text="Select Output Directory", command=select_output_directory)
btn_select_output.pack(pady=10)

btn_create = tk.Button(frame, text="Create", command=create_html)
btn_create.pack(pady=10)

btn_support = tk.Button(frame, text="Consider supporting me", command=open_support_link)
btn_support.pack(pady=10)

root.mainloop()
