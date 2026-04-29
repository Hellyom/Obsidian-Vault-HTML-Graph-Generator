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

# Distinct color for folder nodes
FOLDER_COLOR = "#6b5b95"

def parse_vault(vault_dir):
    """Parse vault to extract files, folders, and wikilinks between files."""
    files = {}  # Key: file_id (filename lowercase, e.g., "note.md")
    links = defaultdict(list)  # Key: source file_id, Value: list of target link strings
    folders = {}  # Key: folder_id (relative path from vault root, e.g., "Projects/Work")
    
    for root, dirs, files_in_dir in os.walk(vault_dir):
        # Process current directory as a folder node
        if root == vault_dir:
            folder_id = "Vault Root"
        else:
            folder_id = os.path.relpath(root, vault_dir)
        
        # Add folder to tracking dict if not already present
        if folder_id not in folders:
            parent_folder_id = None
            if root != vault_dir:
                parent_abs = os.path.dirname(root)
                parent_folder_id = "Vault Root" if parent_abs == vault_dir else os.path.relpath(parent_abs, vault_dir)
            
            folders[folder_id] = {
                "abs_path": root,
                "parent_folder_id": parent_folder_id,
                "name": os.path.basename(root) if root != vault_dir else "Vault Root"
            }
        
        # Process all .md files in this directory
        for file in files_in_dir:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    html_content = markdown.markdown(content)
                    file_id = file.lower()  # Existing behavior: key by filename lowercase
                    files[file_id] = {
                        "content": content,
                        "html": html_content,
                        "parent_folder_id": folder_id,
                        "abs_path": file_path
                    }
                
                # Extract wikilinks, markdown links, and embeds
                link_patterns = [
                    r'\[\[(.*?)\]\]',          # Wikilinks
                    r'\[([^\]]+)\]\(([^)]+)\)', # Markdown links
                    r'!\[\[(.*?)\]\]'           # Embeds
                ]
                for pattern in link_patterns:
                    for match in re.finditer(pattern, content):
                        link = match.group(1)
                        link = link.split('|')[0]  # Remove display text
                        link = link.split('#')[0]   # Remove heading links
                        link = link.strip().lower()
                        links[file_id].append(link)
    
    return files, links, folders

def generate_graph_data(files, links, folders, color_groups):
    """Generate nodes and edges including folder nodes and file-folder connections."""
    def capitalize_first_letter(s):
        return s[0].upper() + s[1:] if s else s
    
    nodes = []
    edges = []
    node_link_count = defaultdict(int)
    
    # 1. Create file nodes (existing behavior + type metadata)
    for file_id, file_info in files.items():
        label = capitalize_first_letter(os.path.splitext(file_id)[0])
        node = {
            "id": file_id,
            "label": label,
            "content": file_info["content"],
            "type": "file",
            "parent_folder_id": file_info["parent_folder_id"]
        }
        nodes.append(node)
    
    # 2. Create folder nodes
    for folder_id, folder_info in folders.items():
        node = {
            "id": folder_id,
            "label": folder_info["name"],
            "type": "folder",
            "color": FOLDER_COLOR,
            "parent_folder_id": folder_info["parent_folder_id"]
        }
        nodes.append(node)
    
    # 3. Create all edges
    # A. Existing file-to-file wikilinks
    for src, dst_list in links.items():
        node_link_count[src] += len(dst_list)
        for dst in dst_list:
            potential_targets = [
                dst,
                dst + '.md',
                os.path.splitext(dst)[0] + '.md'
            ]
            for target in potential_targets:
                if target in files:
                    edges.append({"source": src, "target": target})
                    node_link_count[target] += 1
                    break
    
    # B. File-to-parent-folder edges (subfiles connected to their folder node)
    for file_id, file_info in files.items():
        parent_folder_id = file_info["parent_folder_id"]
        edges.append({"source": file_id, "target": parent_folder_id})
        node_link_count[file_id] += 1
        node_link_count[parent_folder_id] += 1
    
    # C. Folder-to-parent-folder edges (hierarchy representation)
    for folder_id, folder_info in folders.items():
        parent_folder_id = folder_info["parent_folder_id"]
        if parent_folder_id:
            edges.append({"source": folder_id, "target": parent_folder_id})
            node_link_count[folder_id] += 1
            node_link_count[parent_folder_id] += 1
    
    # Assign link counts to all nodes
    for node in nodes:
        node['link_count'] = node_link_count.get(node['id'], 0)
    
    # Assign colors (files use Obsidian color groups, folders use fixed color)
    for node in nodes:
        if node['type'] == 'file':
            node['color'] = get_node_color(node, color_groups)
        else:
            node['color'] = FOLDER_COLOR
    
    # Remove content from nodes to reduce HTML payload size
    for node in nodes:
        if 'content' in node:
            del node['content']
    
    return nodes, edges

def get_node_color(node, color_groups):
    """Get node color from Obsidian's graph color groups (files only)."""
    content = node.get('content', '')
    for group in color_groups:
        if group['query'] and re.search(group['query'], content, re.IGNORECASE):
            return group['color']
    return "#7f7f7f"  # Default gray for unmatched files

def rgb_to_hex(rgb):
    return f"#{rgb:06x}"

def get_obsidian_colors(vault_dir):
    """Load color groups from Obsidian's graph.json config."""
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
    """Generate interactive HTML graph with D3.js, styling folder nodes differently."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { margin:0; padding:0; overflow: hidden; background-color: #1e1e1e; }
            .node { cursor: move; }
            .link { stroke: #999; stroke-opacity: 0.6; }
            text { font-family: Arial, sans-serif; font-size: 12px; pointer-events: none; fill: #fff; }
            .folder-label { font-size: 14px; font-weight: bold; }
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
                .attr("class", d => "node " + d.type)
                .attr("r", function(d) {
                    // Folders are larger than files
                    var base = d.type === 'folder' ? 8 : 5;
                    return base + Math.sqrt(d.link_count);
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
                .attr("class", d => d.type === 'folder' ? "folder-label" : "")
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
        files, links, folders = parse_vault(vault_dir)
        color_groups = get_obsidian_colors(vault_dir)
        nodes, edges = generate_graph_data(files, links, folders, color_groups)
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
root.title("Obsidian Vault Graph Generator (Folder-Aware)")
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
