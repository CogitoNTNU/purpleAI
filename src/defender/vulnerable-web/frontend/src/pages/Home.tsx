import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useNavigate } from "react-router-dom";
import axiosInstance from "@/services/axios";
import { Search } from "lucide-react";
import { Label } from "@/components/ui/label";

type Category = { value: string; label: string };

export default function Home() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

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

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/businesses?q=${encodeURIComponent(searchQuery.trim())}`);
    } else {
      navigate("/businesses");
    }
  };

  return (
    <div className="flex flex-col items-center w-full max-w-4xl mx-auto space-y-12 py-12">
      <section className="text-center space-y-6 max-w-2xl px-4">
        <Label className="text-4xl font-extrabold tracking-tight">
          Find Businesses <span className="text-primary">You Can Trust</span>
        </Label>
        <p className="text-lg text-muted-foreground">
          SecureReview is the best place to start when looking for great
          businesses. Discover great places, read authentic experiences, and
          share your own stories.
        </p>
        <form
          onSubmit={handleSearch}
          className="flex gap-2 max-w-lg mx-auto pt-4 relative"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
            <Input
              placeholder="Search for restaurants, shops..."
              className="pl-10 h-12 text-base shadow-sm"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Button type="submit" size="lg" className="h-12 px-8">
            Search
          </Button>
        </form>
      </section>
      <section className="w-full px-4 text-center space-y-6">
        <Label className="text-2xl font-semibold tracking-tight">
          Browse by Category
        </Label>
        {loading ? (
          <div className="text-sm text-muted-foreground">
            Loading categories...
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 max-w-3xl mx-auto">
            {categories.map((c) => (
              <Button
                key={c.value}
                variant="outline"
                className="text-md"
                size="lg"
                onClick={() =>
                  navigate(
                    `/businesses?category=${encodeURIComponent(c.value)}`
                  )
                }
              >
                {c.label}
              </Button>
            ))}
            <Button
              variant="outline"
              className="text-md"
              onClick={() => navigate("/businesses")}
            >
              View All
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
