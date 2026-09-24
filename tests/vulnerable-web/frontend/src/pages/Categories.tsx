import { useEffect, useState } from "react";
import axiosInstance from "@/services/axios";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useNavigate } from "react-router-dom";

type Category = { value: string; label: string };

export default function Categories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const res = await axiosInstance.get("businesses/categories/");
        setCategories(res.data || []);
      } catch (e) {
        console.error("Failed to fetch categories", e);
      } finally {
        setLoading(false);
      }
    };
    fetchCategories();
  }, []);

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <Label className="text-2xl">Categories</Label>
      </div>
      {loading ? (
        <div className="text-sm text-muted-foreground">
          Loading categories...
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {categories.map((c) => (
            <Button
              key={c.value}
              variant="secondary"
              onClick={() =>
                navigate(`/businesses?category=${encodeURIComponent(c.value)}`)
              }
            >
              {c.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
