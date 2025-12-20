import numpy as np
from collections import Counter
from sklearn.cluster import KMeans
from shapely.geometry import Polygon, LineString
from termcolor import colored 


def parse_entry(entry):
    """Parse an entry into a dictionary of object details."""
    parts = entry.split('|')
    return {
        'id': parts[0],
        'confidence': float(parts[1]),
        'left': float(parts[2]),
        'top': float(parts[3]),
        'right': float(parts[4]),
        'bottom': float(parts[5]),
        'class': parts[6].strip(),
        'filename': parts[7].strip(),
    }

def calculate_line_centroid(line_coords):
    """Calculate the centroid of a line given its start and end coordinates."""
    x1, y1, x2, y2 = line_coords
    return ((x1 + x2) / 2, (y1 + y2) / 2)

def calculate_left_side_centroid(bbox):
    """Calculate the centroid of the left side of a bbox (top-left and bottom-left points)."""
    left, top, right, bottom = bbox
    return (left, (top + bottom) / 2)

def create_polygon_from_bbox(bbox):
    """Create a Shapely polygon from bounding box coordinates."""
    left, top, right, bottom = bbox
    return Polygon([
        (left, top),
        (right, top),
        (right, bottom),
        (left, bottom)
    ])
def check_line_polygon_intersection(polygon_coords,line_coords=[(350, 634), (2016, 894)], ):
    """
    Check if a line intersects or crosses a polygon
    
    Parameters:
    line_coords: tuple of coordinates (x1, y1, x2, y2)
    polygon_coords: list of tuples of polygon vertices [(x1,y1), (x2,y2), ...]
    
    Returns:
    dict: Dictionary containing intersection information
    """
    # Create LineString from coordinates
    # x1, y1, x2, y2 = line_coords
    line = LineString(line_coords)
    if not isinstance(polygon_coords, Polygon):
        polygon = create_polygon_from_bbox(polygon_coords)
    else:
        print(f"Instance coords  entered")
        polygon =  polygon_coords 
    crosses = line.intersects(polygon)
    print(f"Crossed : {crosses}")
    # crosses = line.crosses(polygon)
    if crosses:
        return crosses
    else :
        return False
    
def kmean_clustering(obj_element,centroids,line_coords=(350, 634, 2016, 894),n_clusters=2) -> dict :
    # Convert to numpy array for clustering
    left_side_centroids = np.array(centroids)

    # Perform K-Means clustering
    kmeans = KMeans(n_clusters=n_clusters, random_state=0).fit(left_side_centroids)
    labels = kmeans.labels_
    
    # Calculate distances to line centroid
    line_centroid = calculate_line_centroid(line_coords)
    cluster_centroids = kmeans.cluster_centers_
    distances_to_line_centroid = [
        np.sqrt((centroid[0] - line_centroid[0])**2 + (centroid[1] - line_centroid[1])**2)
        for centroid in cluster_centroids
    ]
    
    # Find the nearest cluster centroid(s)
    min_distance = min(distances_to_line_centroid)
    nearest_cluster_index = distances_to_line_centroid.index(min_distance)
    
    # Collect entries belonging to the nearest cluster
    nearest_cluster_entries = [
        obj for obj, label in zip(obj_element, labels) if label == nearest_cluster_index
    ]

    return nearest_cluster_entries


def check_polygon_overlaps(entries):
    """
    Check for overlapping polygons and return the ones that overlap with others.
    """
    overlapping_entries = []
    polygons = []
    
    # Create polygons for all entries
    for entry in entries:
        obj = entry
        bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
        poly = create_polygon_from_bbox(bbox)
        polygons.append((poly, obj))
    
    # # Check for overlaps
    # for i, (poly1, obj1) in enumerate(polygons):
    #     for j, (poly2, obj2) in enumerate(polygons):
    #         if i != j and poly1.intersects(poly2):
    #             if obj1 not in overlapping_entries:
    #                 overlapping_entries.append(obj1)
    #             if obj2 not in overlapping_entries:
    #                 overlapping_entries.append(obj2)
    for i, (poly1, obj1) in enumerate(polygons):
        for j, (poly2, obj2) in enumerate(polygons):
            if i != j:
                # Check intersection
                if poly1.intersects(poly2):
                    if obj1 not in overlapping_entries:
                        overlapping_entries.append(obj1)
                    if obj2 not in overlapping_entries:
                        overlapping_entries.append(obj2)
                    
                    # Check containment
                    if poly1.contains(poly2):
                        print(f"Object {obj1['id']} ({obj1['class']}) CONTAINS Object {obj2['id']} ({obj2['class']})")
                    elif poly2.contains(poly1):
                        print(f"Object {obj2['id']} ({obj2['class']}) CONTAINS Object {obj1['id']} ({obj1['class']})")
                    else:
                        print(f"Object {obj1['id']} ({obj1['class']}) INTERSECTS Object {obj2['id']} ({obj2['class']})")
    
    if not overlapping_entries:
        print("No overlapping or containing polygons found.")
    print(f"check_polygon_overlaps : {overlapping_entries}")
    return overlapping_entries

def analyze_scene(entries):
    """
    Analyze scene by either checking polygon overlaps or performing clustering,
    depending on the class count distribution.
    """
    # Parse entries and count classes
    parsed_entries = [parse_entry(entry) for entry in entries]
    filtered_entries = [data for data in parsed_entries if data['class'] != 'person']
    print(f"\nfiltered entries :  {filtered_entries} ")
    del parsed_entries
    class_counts = Counter(obj['class'] for obj in filtered_entries if obj['class'] != 'person')
    # Check if all classes have count of 1
    print(f"\nInital class_count :  {len(class_counts)}")
    all_singles = all(count == 1 for count in class_counts.values())
    
    if all_singles and (len(class_counts) >1 ):
        print("\nsingle detect if ")
        print("\nClasses:",dict(class_counts))
        # Perform polygon overlap analysis
        overlapping_entries = check_polygon_overlaps(filtered_entries)
        print(f"Retruned overlap entry :  {overlapping_entries}\n")
        print (f"Before if len (Overlap) : {len(overlapping_entries)}\n")
        if len(overlapping_entries) > 2 :
            print("Entering Overlap Issued")
            bbox_centroids = []
            obj_element = []
            for entry in overlapping_entries:
                obj = entry
                bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
                obj_element.append(obj)
                centroid = calculate_left_side_centroid(bbox)
                bbox_centroids.append(centroid)
            overlap_filter_result = kmean_clustering(obj_element,bbox_centroids)
            del obj_element, bbox_centroids
            print(f"\nOverlapping filtered  Entries : {overlap_filter_result}")
            # return {'result': overlapping_entries}
            return overlap_filter_result
        else:
            print("\nEnter Else Overlap ")
            result = [] 
            for element in overlapping_entries:
                obj = element
                bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
                if check_line_polygon_intersection(bbox):
                    # return overlapping_entries
                    result.append(element)
                    print("appended")
                else:
                    print("Overlapped element betrayed ")
            # del element,obj
            print(f"Resulted : {result}") 
            if (not result):
                print("Subtracted loop")
                subtracted = [ i for i in filtered_entries if i not in overlapping_entries] 
                print(f"Subtracted {subtracted}")
                result_element = []
                for element in subtracted:
                    obj = element
                    bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
                    if check_line_polygon_intersection(bbox):
                        result_element.append(element)
                print("Subtracted list element succeeded")
                return result_element
            else:
                return result 
    elif(len(class_counts)>2):

        print("Pssed Elif ")
        overlapping_entries = check_polygon_overlaps(filtered_entries)
        print(f" Elif Retruned overlap entry :  {overlapping_entries}\n")
        # print (f"Before if len (Overlap) : {len(overlapping_entries)}\n")
        if len(overlapping_entries) > 2 :
            print("Entering Overlap Issued")
            bbox_centroids = []
            obj_element = []
            for entry in overlapping_entries:
                obj = entry
                bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
                obj_element.append(obj)
                centroid = calculate_left_side_centroid(bbox)
                bbox_centroids.append(centroid)
            overlap_filter_result = kmean_clustering(obj_element,bbox_centroids)
            del obj_element, bbox_centroids
            print(f"\nOverlapping filtered  Entries : {overlap_filter_result}")
            # return {'result': overlapping_entries}
            return overlap_filter_result
        else:
            print("\nEnter Else Overlap ")
            result = [] 
            for element in overlapping_entries:
                obj = element
                bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
                if check_line_polygon_intersection(bbox):
                    # return overlapping_entries
                    result.append(element)
                    print("appended")
                else:
                    print("Overlapped element betrayed ")
            # del element,obj
            print(f"Resulted : {result}") 
            if (not result):
                print("Subtracted loop")
                subtracted = [ i for i in filtered_entries if i not in overlapping_entries] 
                print(f"Subtracted {subtracted}")
                result_element = []
                for element in subtracted:
                    obj = element
                    bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
                    if check_line_polygon_intersection(bbox):
                        result_element.append(element)
                print("Subtracted list element succeeded")
                return result_element
            else:
                return result
    else:
        print("Final Else\n")
        obj_element = [] 
        print(f"class_count :  {len(class_counts)}")
        for entry in filtered_entries:
                obj = entry
                bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
                # obj_element.append(obj)
                if check_line_polygon_intersection(bbox):
                        obj_element.append(entry)
        return obj_element
        #return filtered_entries
    
    # If not all singles or no overlaps found, proceed with original clustering analysis
    bbox1_centroids = []
    obj_element = []
    print("Not passes Overlapping check")
    for entry in filtered_entries:
        obj = entry
        bbox = (obj['left'], obj['top'], obj['right'], obj['bottom'])
        obj_element.append(obj)
        left_side_centroid = calculate_left_side_centroid(bbox)
        print("Arrays: ",bbox1_centroids)
        bbox1_centroids.append(left_side_centroid)
    result = kmean_clustering(obj_element,bbox1_centroids)
    del obj_element, bbox1_centroids
    print(colored("Hey Jesus !!!!!! \nPLease make some miracle by using Kmeans !","green"))
    return result
    # print("Thank You Jesus!!!!  to Use Kmeans  for myy model !!! ")
